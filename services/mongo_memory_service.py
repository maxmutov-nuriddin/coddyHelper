"""
MongoDB Atlas Kognitiv Miya Xotira Xizmati (CoddyAgentBrain).
Barcha ma'lumotlar 5 ta modulli bo'lim (kolleksiyalar)da o'chmas qilib saqlanadi:
1. brain_cognitive: learned_insights, cognitive_growth, reflection_journal
2. brain_mentor: daily_plans, smart_reminders, saved_locations, wellbeing_logs
3. brain_frontline: conversations, student_profiles, user_quotas
4. brain_knowledge: curriculum, precomputed_answers
5. system_core: global_settings, security_blacklist, telemetry_metrics

Dual-Persistence: Agar tarmoqda uzilish bo'lsa, lokal SQLite bilan xavfsiz ishlaydi va qayta sinxronlanadi.
"""

import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from config import config

logger = logging.getLogger(__name__)

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    logger.warning("pymongo o'rnatilmagan! MongoDB xotirasi faollashmadi.")


class MongoMemoryService:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or config.mongodb_uri
        self.db_name = db_name or config.mongodb_db_name or "CoddyAgentBrain"
        self._client: Optional[MongoClient] = None
        self._db: Any = None
        self._is_connected: bool = False
        self._init_mongo()

    def _init_mongo(self) -> None:
        """MongoDB Atlas bilan xavfsiz ulanish o'rnatadi va indekslarni tayyorlaydi."""
        if not PYMONGO_AVAILABLE or not self.uri:
            self._is_connected = False
            return

        try:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                maxPoolSize=20,
            )
            # Test ping
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            self._is_connected = True
            logger.info("🧠 MongoDB Atlas (%s) ga muvaffaqiyatli ulandi!", self.db_name)
            self._ensure_indexes()
        except Exception as e:
            self._is_connected = False
            logger.warning("MongoDB Atlas'ga ulanishda ogohlantirish (Offline kesh ishlaydi): %s", e)

    def is_connected(self) -> bool:
        now = time.time()
        # Agar mijoz mavjud bo'lmasa yoki uzilgan bo'lsa, har 5 soniyada qayta ulanishga urinish
        if not self._is_connected or self._client is None:
            if now - getattr(self, "_last_reconnect_attempt", 0) > 5.0:
                self._last_reconnect_attempt = now
                self._init_mongo()
            if not self._is_connected or self._client is None:
                return False

        # Har bir so'rovda Atlas'ga ping yubormaslik (30 soniyalik kesh)
        if now - getattr(self, "_last_ping_time", 0) < 30.0:
            return self._is_connected

        try:
            self._client.admin.command("ping")
            self._last_ping_time = now
            self._is_connected = True
            return True
        except Exception:
            self._is_connected = False
            return False

    def _ensure_indexes(self) -> None:
        """Kolleksiyalar uchun tezkor qidiruv indekslarini hosil qiladi."""
        if not self._is_connected or self._db is None:
            return
        try:
            # 1. brain_frontline.conversations
            self._db["brain_frontline.conversations"].create_index([("chat_id", 1), ("id", -1)])
            # 2. brain_mentor.smart_reminders
            self._db["brain_mentor.smart_reminders"].create_index([("is_sent", 1), ("remind_at", 1)])
            # 3. brain_frontline.student_profiles
            self._db["brain_frontline.student_profiles"].create_index([("user_id", 1)], unique=True)
            # 4. brain_cognitive.learned_insights
            self._db["brain_cognitive.learned_insights"].create_index([("key", 1)], unique=True)
            # 5. system_core.global_settings
            self._db["system_core.global_settings"].create_index([("key", 1)], unique=True)
            # 6. brain_mentor.daily_plans
            self._db["brain_mentor.daily_plans"].create_index([("date", 1)])
            # 7. system_core.security_blacklist
            self._db["system_core.security_blacklist"].create_index([("user_id", 1)], unique=True)
            # 8. brain_cognitive.mentor_lexicon
            self._db["brain_cognitive.mentor_lexicon"].create_index([("term", 1)], unique=True)
            # 9. brain_cognitive.self_mistakes
            self._db["brain_cognitive.self_mistakes"].create_index([("created_at", -1)])
            # 10. brain_cognitive.daily_debriefs
            self._db["brain_cognitive.daily_debriefs"].create_index([("date", 1)], unique=True)
            # 11. system_core.user_subscriptions
            self._db["system_core.user_subscriptions"].create_index([("user_id", 1)], unique=True)
            self._db["system_core.user_subscriptions"].create_index([("group_id", 1)])
            logger.info("🧠 MongoDB Kognitiv Miya indekslari to'liq tasdiqlandi.")
        except Exception as e:
            logger.warning("MongoDB indekslarini sozlashda ogohlantirish: %s", e)

    # ==========================================
    # 1. brain_frontline (Chatlar & O'quvchilar)
    # ==========================================
    def add_conversation_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        sender_id: Optional[int] = None,
        model_used: str = "",
        tokens: int = 0,
    ) -> bool:
        if not self.is_connected():
            return False
        try:
            doc = {
                "chat_id": chat_id,
                "sender_id": sender_id,
                "role": role,
                "content": content,
                "model_used": model_used,
                "tokens": tokens,
                "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
                "timestamp": time.time(),
            }
            self._db["brain_frontline.conversations"].insert_one(doc)
            return True
        except Exception as e:
            logger.error("MongoDB conversations xatolik: %s", e)
            return False

    def get_conversation_history(self, chat_id: int, limit: int = 15, sender_id: Optional[int] = None) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            query: dict[str, Any] = {"chat_id": chat_id}
            if sender_id is not None and chat_id < 0:
                query["$or"] = [{"sender_id": sender_id}, {"sender_id": None}]
            cursor = (
                self._db["brain_frontline.conversations"]
                .find(query)
                .sort("timestamp", -1)
                .limit(limit)
            )
            docs = list(cursor)
            docs.reverse()
            return docs
        except Exception as e:
            logger.error("MongoDB get_conversation_history xatolik: %s", e)
            return []

    def clear_conversation_history(self, chat_id: int) -> bool:
        if not self.is_connected():
            return False
        try:
            self._db["brain_frontline.conversations"].delete_many({"chat_id": chat_id})
            return True
        except Exception as e:
            logger.error("MongoDB clear_conversation_history xatolik: %s", e)
            return False

    # ==========================================
    # 2. brain_cognitive (O'rganuvchi Ong & Saboqlar)
    # ==========================================
    def save_learned_insight(
        self,
        key: str,
        content: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "chat",
    ) -> bool:
        if not self.is_connected():
            return False
        try:
            now_dt = datetime.now(ZoneInfo("Asia/Tashkent"))
            self._db["brain_cognitive.learned_insights"].update_one(
                {"key": key},
                {
                    "$set": {
                        "key": key,
                        "content": content,
                        "category": category,
                        "confidence_score": confidence,
                        "source": source,
                        "updated_at": now_dt,
                    },
                    "$setOnInsert": {"created_at": now_dt},
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_learned_insight xatolik: %s", e)
            return False

    def get_all_learned_insights(self, category: Optional[str] = None) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            q = {"category": category} if category else {}
            return list(self._db["brain_cognitive.learned_insights"].find(q).sort("updated_at", -1))
        except Exception as e:
            logger.error("MongoDB get_all_learned_insights xatolik: %s", e)
            return []

    def delete_learned_insight(self, target: str) -> bool:
        """MongoDB dan saboq/bilimni ObjectId yoki kalit/mavzusi bo'yicha o'chiradi."""
        if not self.is_connected() or not target:
            return False
        try:
            import re
            from bson import ObjectId
            col = self._db["brain_cognitive.learned_insights"]
            target_str = str(target).strip()
            # 1. ObjectId bo'yicha o'chirish
            if ObjectId.is_valid(target_str):
                res = col.delete_one({"_id": ObjectId(target_str)})
                if res.deleted_count > 0:
                    return True
            # 2. Kalit / Mavzu bo'yicha o'chirish
            res = col.delete_one({"key": target_str})
            if res.deleted_count > 0:
                return True
            # 3. Registrga sezgir bo'lmagan holda o'chirish
            res = col.delete_one({"key": {"$regex": f"^{re.escape(target_str)}$", "$options": "i"}})
            return res.deleted_count > 0
        except Exception as e:
            logger.error("MongoDB delete_learned_insight xatolik: %s", e)
            return False

    def approve_learned_insight(self, target: str) -> bool:
        """MongoDB da saboqni tasdiqlangan (verified_insight) deb belgilaydi."""
        if not self.is_connected() or not target:
            return False
        try:
            import re
            from bson import ObjectId
            col = self._db["brain_cognitive.learned_insights"]
            target_str = str(target).strip()
            if ObjectId.is_valid(target_str):
                res = col.update_one({"_id": ObjectId(target_str)}, {"$set": {"category": "verified_insight", "is_verified": True}})
                if res.modified_count > 0:
                    return True
            res = col.update_one({"key": target_str}, {"$set": {"category": "verified_insight", "is_verified": True}})
            if res.modified_count > 0:
                return True
            res = col.update_one({"key": {"$regex": f"^{re.escape(target_str)}$", "$options": "i"}}, {"$set": {"category": "verified_insight", "is_verified": True}})
            return res.modified_count > 0
        except Exception as e:
            logger.error("MongoDB approve_learned_insight xatolik: %s", e)
            return False

    def update_cognitive_growth(self, xp_gain: int = 10, iq_points: int = 1, reason: str = "") -> dict:
        """Agent IQ va XP sini oshiradi va tarixga qayd qiladi."""
        if not self.is_connected():
            return {"iq": 140, "xp": 100, "level": 1}
        try:
            col = self._db["brain_cognitive.cognitive_growth"]
            current = col.find_one({"_id": "current_stats"})
            if not current:
                current = {
                    "_id": "current_stats",
                    "iq_score": 140,
                    "xp": 500,
                    "level": 3,
                    "history": [],
                }
            current["xp"] = current.get("xp", 500) + xp_gain
            current["iq_score"] = current.get("iq_score", 140) + iq_points
            current["level"] = max(1, current["xp"] // 300)
            
            log_entry = {
                "xp_gain": xp_gain,
                "iq_gain": iq_points,
                "reason": reason,
                "time": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            current.setdefault("history", []).append(log_entry)
            if len(current["history"]) > 100:
                current["history"] = current["history"][-100:]

            col.update_one({"_id": "current_stats"}, {"$set": current}, upsert=True)
            return current
        except Exception as e:
            logger.error("MongoDB update_cognitive_growth xatolik: %s", e)
            return {"iq": 140, "xp": 100, "level": 1}

    def get_cognitive_stats(self) -> dict:
        if not self.is_connected():
            return {"iq": 140, "xp": 500, "level": 3}
        try:
            current = self._db["brain_cognitive.cognitive_growth"].find_one({"_id": "current_stats"})
            if not current:
                return {"iq": 140, "xp": 500, "level": 3}
            return {
                "iq": current.get("iq_score", 140),
                "xp": current.get("xp", 500),
                "level": current.get("level", 3),
            }
        except Exception:
            return {"iq": 140, "xp": 500, "level": 3}

    def get_storage_stats(self) -> dict:
        """MongoDB Atlas xotira hajmi, hujjatlar soni va qolgan bo'sh joy statistikasini hisoblaydi."""
        if not self.is_connected():
            return {
                "ok": False,
                "connected": False,
                "message": "MongoDB Atlas bilan hozircha ulanish yo'q (mahalliy SQLite kesh ishlamoqda)",
            }
        try:
            db_stats = self._db.command("dbstats")
            # MongoDB Atlas M0 bepul klaster limiti: 512 MB
            max_mb = 512.0
            storage_bytes = db_stats.get("storageSize", 0)
            data_bytes = db_stats.get("dataSize", 0)
            storage_mb = round(storage_bytes / (1024 * 1024), 2)
            data_mb = round(data_bytes / (1024 * 1024), 2)
            free_mb = max(0.0, round(max_mb - storage_mb, 2))
            used_pct = min(100.0, round((storage_mb / max_mb) * 100, 2))
            objects_count = db_stats.get("objects", 0)
            collections_count = db_stats.get("collections", 0)

            return {
                "ok": True,
                "connected": True,
                "storage_used_mb": storage_mb,
                "data_used_mb": data_mb,
                "storage_free_mb": free_mb,
                "storage_limit_mb": max_mb,
                "used_percentage": used_pct,
                "free_percentage": round(100.0 - used_pct, 2),
                "total_documents": objects_count,
                "total_collections": collections_count,
                "db_name": getattr(self._db, "name", "coddy_brain"),
            }
        except Exception as e:
            logger.error("MongoDB get_storage_stats xatolik: %s", e)
            return {"ok": False, "connected": True, "error": str(e)}

    # -----------------------------------------------------------
    # Mentor Lexicon (Mentor tili, qisqartmalari va slengi)
    # -----------------------------------------------------------
    def save_mentor_lexicon(
        self, term: str, meaning: str, example: str = "", confidence: float = 1.0
    ) -> bool:
        if not self.is_connected() or not term or not meaning:
            return False
        try:
            doc = {
                "term": term.strip().lower(),
                "meaning": meaning.strip(),
                "example": example.strip(),
                "confidence": confidence,
                "updated_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_cognitive.mentor_lexicon"].update_one(
                {"term": doc["term"]},
                {"$set": doc, "$setOnInsert": {"created_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_mentor_lexicon xatolik: %s", e)
            return False

    def get_all_mentor_lexicon(self, limit: int = 100) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(
                self._db["brain_cognitive.mentor_lexicon"]
                .find()
                .sort("updated_at", -1)
                .limit(limit)
            )
        except Exception as e:
            logger.error("MongoDB get_all_mentor_lexicon xatolik: %s", e)
            return []

    def delete_mentor_lexicon(self, term: str) -> bool:
        if not self.is_connected() or not term:
            return False
        try:
            self._db["brain_cognitive.mentor_lexicon"].delete_one({"term": term.strip().lower()})
            return True
        except Exception as e:
            logger.error("MongoDB delete_mentor_lexicon xatolik: %s", e)
            return False

    # -----------------------------------------------------------
    # Self-Mistakes & Reflection (O'z xatolaridan saboq chiqarish)
    # -----------------------------------------------------------
    def save_self_mistake(
        self, situation: str, mistake: str, correction: str, rule: str
    ) -> bool:
        if not self.is_connected() or not rule:
            return False
        try:
            doc = {
                "situation": situation.strip(),
                "mistake": mistake.strip(),
                "correction": correction.strip(),
                "rule": rule.strip(),
                "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_cognitive.self_mistakes"].insert_one(doc)
            return True
        except Exception as e:
            logger.error("MongoDB save_self_mistake xatolik: %s", e)
            return False

    def get_recent_self_mistakes(self, limit: int = 50) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(
                self._db["brain_cognitive.self_mistakes"]
                .find()
                .sort("created_at", -1)
                .limit(limit)
            )
        except Exception as e:
            logger.error("MongoDB get_recent_self_mistakes xatolik: %s", e)
            return []

    # -----------------------------------------------------------
    # Daily Debriefs (Soat 20:00 dagi hisobotlar tarixi)
    # -----------------------------------------------------------
    def save_daily_debrief(self, date_str: str, report_text: str, stats: dict = None) -> bool:
        if not self.is_connected() or not date_str:
            return False
        try:
            doc = {
                "date": date_str,
                "report_text": report_text,
                "stats": stats or {},
                "sent_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_cognitive.daily_debriefs"].update_one(
                {"date": date_str},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_daily_debrief xatolik: %s", e)
            return False

    def is_daily_debrief_sent(self, date_str: str) -> bool:
        if not self.is_connected():
            return False
        try:
            return bool(self._db["brain_cognitive.daily_debriefs"].find_one({"date": date_str}))
        except Exception:
            return False

    # ==========================================
    # 3. brain_mentor (Vazifalar, Rejalar & Manzillar)
    # ==========================================
    def add_daily_plan(self, date_str: str, title: str, plan_time: str = "", category: str = "vazifa") -> bool:
        if not self.is_connected():
            return False
        try:
            doc = {
                "date": date_str,
                "title": title,
                "plan_time": plan_time,
                "category": category,
                "is_completed": False,
                "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_mentor.daily_plans"].insert_one(doc)
            return True
        except Exception as e:
            logger.error("MongoDB add_daily_plan xatolik: %s", e)
            return False

    def get_daily_plans(self, date_str: str) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(self._db["brain_mentor.daily_plans"].find({"date": date_str}).sort("plan_time", 1))
        except Exception as e:
            logger.error("MongoDB get_daily_plans xatolik: %s", e)
            return []

    def set_plan_completed(self, plan_id: str, is_completed: bool = True) -> bool:
        if not self.is_connected():
            return False
        try:
            from bson import ObjectId
            _id = ObjectId(plan_id) if ObjectId.is_valid(plan_id) else plan_id
            self._db["brain_mentor.daily_plans"].update_one(
                {"$or": [{"_id": _id}, {"title": plan_id}]},
                {"$set": {"is_completed": is_completed, "completed_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
            )
            return True
        except Exception as e:
            logger.error("MongoDB set_plan_completed xatolik: %s", e)
            return False

    def add_smart_reminder(
        self,
        chat_id: int,
        creator_id: int,
        text: str,
        remind_at: str,
        recurrence: str = "once",
        sqlite_id: int = 0,
    ) -> bool:
        if not self.is_connected():
            return False
        try:
            doc = {
                "chat_id": chat_id,
                "creator_id": creator_id,
                "text": text,
                "remind_at": remind_at,
                "recurrence": recurrence,
                "is_sent": False,
                "sqlite_id": sqlite_id,
                "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_mentor.smart_reminders"].insert_one(doc)
            return True
        except Exception as e:
            logger.error("MongoDB add_smart_reminder xatolik: %s", e)
            return False

    def get_pending_reminders(self, current_iso_time: str) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(
                self._db["brain_mentor.smart_reminders"].find(
                    {"is_sent": False, "remind_at": {"$lte": current_iso_time}}
                )
            )
        except Exception as e:
            logger.error("MongoDB get_pending_reminders xatolik: %s", e)
            return []

    def mark_reminder_sent(self, reminder_id: Any) -> bool:
        if not self.is_connected():
            return False
        try:
            from bson import ObjectId
            target_str = str(reminder_id).strip()
            query = None
            if ObjectId.is_valid(target_str):
                query = {"_id": ObjectId(target_str)}
            elif target_str.isdigit():
                # SQLite ID orqali MongoDB'da qidirish
                query = {"sqlite_id": int(target_str)}
            else:
                query = {"_id": target_str}

            if query:
                self._db["brain_mentor.smart_reminders"].update_many(
                    query,
                    {"$set": {"is_sent": True, "sent_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                )
            return True
        except Exception as e:
            logger.error("MongoDB mark_reminder_sent xatolik: %s", e)
            return False

    def save_location(self, name: str, lat: float, long: float, details: str = "") -> bool:
        if not self.is_connected():
            return False
        try:
            gmaps = f"https://www.google.com/maps?q={lat},{long}"
            yandex = f"https://yandex.com/maps/?pt={long},{lat}&z=16&l=map"
            self._db["brain_mentor.saved_locations"].update_one(
                {"name": name.strip().lower()},
                {
                    "$set": {
                        "name": name.strip().lower(),
                        "display_name": name.strip(),
                        "lat": lat,
                        "long": long,
                        "details": details,
                        "google_maps": gmaps,
                        "yandex_maps": yandex,
                        "updated_at": datetime.now(ZoneInfo("Asia/Tashkent")),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_location xatolik: %s", e)
            return False

    def get_saved_locations(self) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(self._db["brain_mentor.saved_locations"].find().sort("updated_at", -1))
        except Exception as e:
            logger.error("MongoDB get_saved_locations xatolik: %s", e)
            return []

    # ==========================================
    # 4. brain_knowledge & system_core
    # ==========================================
    def set_setting(self, key: str, value: str) -> bool:
        if not self.is_connected():
            return False
        try:
            self._db["system_core.global_settings"].update_one(
                {"key": key},
                {"$set": {"key": key, "value": value, "updated_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB set_setting xatolik: %s", e)
            return False

    def get_setting(self, key: str, default: str = "") -> str:
        if not self.is_connected():
            return default
        try:
            doc = self._db["system_core.global_settings"].find_one({"key": key})
            return doc["value"] if doc and "value" in doc else default
        except Exception:
            return default

    def get_all_settings(self) -> dict[str, str]:
        if not self.is_connected():
            return {}
        try:
            docs = self._db["system_core.global_settings"].find()
            return {d["key"]: d["value"] for d in docs if "key" in d and "value" in d}
        except Exception:
            return {}

    def blacklist_user(self, user_id: int, username: str = "", reason: str = "") -> bool:
        if not self.is_connected():
            return False
        try:
            self._db["system_core.security_blacklist"].update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "username": username,
                        "reason": reason,
                        "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB blacklist_user xatolik: %s", e)
            return False

    def is_user_blacklisted(self, user_id: int) -> bool:
        if not self.is_connected():
            return False
        try:
            return bool(self._db["system_core.security_blacklist"].find_one({"user_id": user_id}))
        except Exception:
            return False

    def unblacklist_user(self, user_id: int) -> bool:
        if not self.is_connected():
            return False
        try:
            self._db["system_core.security_blacklist"].delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error("MongoDB unblacklist_user xatolik: %s", e)
            return False

    def get_all_blacklisted_users(self) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(self._db["system_core.security_blacklist"].find().sort("created_at", -1))
        except Exception:
            return []

    # ==========================================
    # Student Profiles (O'quvchilar)
    # ==========================================
    def upsert_student_profile(
        self,
        user_id: int,
        full_name: str,
        username: str = "",
        group_name: str = "",
        status: str = "yaxshi",
        strengths: str = "",
        weaknesses: str = "",
        mentor_notes: str = "",
    ) -> bool:
        if not self.is_connected() or not user_id:
            return False
        try:
            doc = {
                "user_id": user_id,
                "full_name": full_name,
                "username": username,
                "group_name": group_name,
                "status": status,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "mentor_notes": mentor_notes,
                "updated_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            }
            self._db["brain_frontline.student_profiles"].update_one(
                {"user_id": user_id},
                {"$set": doc, "$setOnInsert": {"created_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB upsert_student_profile xatolik: %s", e)
            return False

    def get_all_student_profiles(self) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            return list(self._db["brain_frontline.student_profiles"].find().sort("full_name", 1))
        except Exception as e:
            logger.error("MongoDB get_all_student_profiles xatolik: %s", e)
            return []

    def delete_student_profile(self, user_id: int) -> bool:
        if not self.is_connected() or not user_id:
            return False
        try:
            self._db["brain_frontline.student_profiles"].delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error("MongoDB delete_student_profile xatolik: %s", e)
            return False

    # ==========================================
    # Smart Reminders (Eslatmalar)
    # ==========================================
    def delete_smart_reminder(self, reminder_id: Any, text: str = "", chat_id: int = 0) -> bool:
        if not self.is_connected():
            return False
        try:
            from bson import ObjectId
            target_str = str(reminder_id).strip()
            queries = []
            if ObjectId.is_valid(target_str):
                queries.append({"_id": ObjectId(target_str)})
            if target_str.isdigit():
                queries.append({"sqlite_id": int(target_str)})
            if text:
                q_text = {"text": text}
                if chat_id:
                    q_text["chat_id"] = chat_id
                queries.append(q_text)
            if queries:
                self._db["brain_mentor.smart_reminders"].delete_many({"$or": queries})
                return True
            return False
        except Exception as e:
            logger.error("MongoDB delete_smart_reminder xatolik: %s", e)
            return False

    def get_all_active_reminders(self, limit: int = 100) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
            # Muddati o'tib ketgan eslatmalarni avtomatik is_sent=True deb belgilash
            try:
                self._db["brain_mentor.smart_reminders"].update_many(
                    {"is_sent": False, "remind_at": {"$lt": now_str}},
                    {"$set": {"is_sent": True, "sent_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                )
            except Exception:
                pass
            return list(
                self._db["brain_mentor.smart_reminders"]
                .find({"is_sent": False})
                .sort("remind_at", 1)
                .limit(limit)
            )
        except Exception as e:
            logger.error("MongoDB get_all_active_reminders xatolik: %s", e)
            return []

    # ==========================================
    # Precomputed Answers (Kesh yechimlar)
    # ==========================================


    def save_precomputed_answer(
        self, topic: str, question_pattern: str, answer_text: str, owner_id: int = 0
    ) -> bool:
        if not self.is_connected() or not question_pattern or not answer_text:
            return False
        try:
            doc = {
                "topic": topic,
                "question_pattern": question_pattern,
                "answer_text": answer_text,
                "owner_id": owner_id,
                "usage_count": 0,
                "created_at": datetime.utcnow()
            }
            self._db["brain_knowledge.precomputed_answers"].update_one(
                {"question_pattern": question_pattern, "owner_id": owner_id},
                {"$setOnInsert": doc},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_precomputed_answer xatolik: %s", e)
            return False

    def delete_precomputed_answer(self, target: Any) -> bool:
        if not self.is_connected() or not target:
            return False
        try:
            from bson import ObjectId
            t_str = str(target).strip()
            if ObjectId.is_valid(t_str):
                self._db["brain_knowledge.precomputed_answers"].delete_one({"_id": ObjectId(t_str)})
                return True
            self._db["brain_knowledge.precomputed_answers"].delete_many(
                {"$or": [{"clean_question": t_str.lower()}, {"topic": t_str}]}
            )
            return True
        except Exception as e:
            logger.error("MongoDB delete_precomputed_answer xatolik: %s", e)
            return False


    def get_all_precomputed_answers(self, limit: int = 100, owner_id: int = 0) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            query = {}
            if owner_id:
                query["$or"] = [{"owner_id": owner_id}, {"owner_id": 0}, {"owner_id": {"$exists": False}}]
            docs = list(self._db["brain_knowledge.precomputed_answers"].find(query).limit(limit))
            result = []
            for d in docs:
                q_pat = d.get("question_pattern") or d.get("clean_question") or d.get("trigger_pattern") or ""
                ans = d.get("answer_text") or d.get("response_text") or ""
                if q_pat and ans:
                    result.append({
                        "id": str(d.get("_id", "")),
                        "topic": d.get("topic", "Umumiy"),
                        "question_pattern": q_pat,
                        "answer_text": ans,
                        "usage_count": d.get("usage_count", 0),
                        "created_at": str(d.get("created_at", "")),
                    })
            return result
        except Exception as e:
            logger.error("MongoDB get_all_precomputed_answers xatolik: %s", e)
            return []

    # ==========================================
    # Active Inquiries (Borib so'rab, aniqlashtirib kelish)
    # ==========================================
    def save_active_inquiry(self, doc: dict) -> bool:
        if not self.is_connected() or not doc:
            return False
        try:
            inquiry_data = dict(doc)
            inquiry_data["updated_at"] = datetime.now(ZoneInfo("Asia/Tashkent"))
            inquiry_id = inquiry_data.get("inquiry_id")
            if inquiry_id:
                self._db["brain_frontline.active_inquiries"].update_one(
                    {"inquiry_id": inquiry_id},
                    {"$set": inquiry_data, "$setOnInsert": {"created_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                    upsert=True,
                )
            else:
                inquiry_data["created_at"] = datetime.now(ZoneInfo("Asia/Tashkent"))
                self._db["brain_frontline.active_inquiries"].insert_one(inquiry_data)
            return True
        except Exception as e:
            logger.error("MongoDB save_active_inquiry xatolik: %s", e)
            return False

    def update_active_inquiry_status(self, inquiry_id: int, status: str, result_summary: str = "") -> bool:
        if not self.is_connected() or not inquiry_id:
            return False
        try:
            self._db["brain_frontline.active_inquiries"].update_one(
                {"inquiry_id": inquiry_id},
                {
                    "$set": {
                        "status": status,
                        "result_summary": result_summary,
                        "updated_at": datetime.now(ZoneInfo("Asia/Tashkent")),
                    }
                },
            )
            return True
        except Exception as e:
            logger.error("MongoDB update_active_inquiry_status xatolik: %s", e)
            return False

    def save_student_weakness(self, student_id: int, topic: str, question: str = "") -> bool:
        """O'quvchining zaif mavzusini MongoDB Atlas da yangilaydi."""
        if not self.is_connected() or not student_id or not topic:
            return False
        try:
            self._db["brain_frontline.student_weaknesses"].update_one(
                {"student_id": student_id, "topic": topic.strip().lower()},
                {
                    "$inc": {"error_count": 1},
                    "$set": {
                        "last_question": (question or "").strip()[:300],
                        "last_seen": datetime.now(ZoneInfo("Asia/Tashkent")),
                    },
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_student_weakness xatolik: %s", e)
            return False

    def get_student_weaknesses(self, student_id: int) -> list[dict]:
        """O'quvchining zaif mavzularini MongoDB Atlas dan oladi."""
        if not self.is_connected() or not student_id:
            return []
        try:
            cursor = self._db["brain_frontline.student_weaknesses"].find(
                {"student_id": student_id}
            ).sort("error_count", -1).limit(5)
            res = []
            for doc in cursor:
                res.append({
                    "topic": doc.get("topic"),
                    "error_count": doc.get("error_count", 1),
                    "last_question": doc.get("last_question", ""),
                    "last_seen": str(doc.get("last_seen", "")),
                })
            return res
        except Exception as e:
            logger.error("MongoDB get_student_weaknesses xatolik: %s", e)
            return []

    def save_user_dossier(
        self,
        user_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        bio: str = "",
        channel_username: str = "",
        channel_summary: str = "",
        photo_count: int = 0,
        has_stories: bool = False,
        dossier_text: str = "",
        common_chats: str = "",
    ) -> bool:
        """Miya 5 dosyesini MongoDB Atlas'da saqlaydi."""
        if not self.is_connected() or not user_id:
            return False
        try:
            self._db["brain_frontline.user_dossiers"].update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "username": username or "",
                        "first_name": first_name or "",
                        "last_name": last_name or "",
                        "phone": phone or "",
                        "bio": bio or "",
                        "channel_username": channel_username or "",
                        "channel_summary": channel_summary or "",
                        "photo_count": photo_count,
                        "has_stories": bool(has_stories),
                        "dossier_text": dossier_text,
                        "common_chats": common_chats or "",
                        "analyzed_at": datetime.now(ZoneInfo("Asia/Tashkent")),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_user_dossier xatolik: %s", e)
            return False

    def is_user_dossier_exists(self, user_id: int) -> bool:
        """MongoDB'da dosye borligini tekshiradi."""
        if not self.is_connected() or not user_id:
            return False
        try:
            return self._db["brain_frontline.user_dossiers"].count_documents({"user_id": user_id}, limit=1) > 0
        except Exception as e:
            logger.debug("MongoDB is_user_dossier_exists xatolik: %s", e)
            return False

    def get_dossier_count(self) -> int:
        """MongoDB'dagi jami dosyelar sonini qaytaradi."""
        if not self.is_connected():
            return 0
        try:
            return self._db["brain_frontline.user_dossiers"].count_documents({})
        except Exception:
            return 0

    def get_all_user_dossiers(self, query: str = "", limit: int = 100) -> list[dict]:
        """MongoDB'dan dosyelarni qidiruv bilan qaytaradi."""
        if not self.is_connected():
            return []
        try:
            flt = {}
            if query and query.strip():
                regex = {"$regex": query.strip(), "$options": "i"}
                flt = {
                    "$or": [
                        {"first_name": regex},
                        {"last_name": regex},
                        {"username": regex},
                        {"phone": regex},
                        {"bio": regex},
                        {"dossier_text": regex},
                        {"common_chats": regex},
                    ]
                }
            docs = self._db["brain_frontline.user_dossiers"].find(flt).sort("analyzed_at", -1).limit(limit)
            result = []
            for d in docs:
                result.append({
                    "user_id": d.get("user_id"),
                    "username": d.get("username", ""),
                    "first_name": d.get("first_name", ""),
                    "last_name": d.get("last_name", ""),
                    "phone": d.get("phone", ""),
                    "bio": d.get("bio", ""),
                    "channel_username": d.get("channel_username", ""),
                    "channel_summary": d.get("channel_summary", ""),
                    "photo_count": d.get("photo_count", 0),
                    "has_stories": bool(d.get("has_stories")),
                    "dossier_text": d.get("dossier_text", ""),
                    "common_chats": d.get("common_chats", ""),
                    "analyzed_at": str(d.get("analyzed_at") or ""),
                })
            return result
        except Exception as e:
            logger.error("MongoDB get_all_user_dossiers xatolik: %s", e)
            return []

    def get_stale_user_dossier_ids(self, days: int = 3, limit: int = 200) -> list[int]:
        """MongoDB'dan oxirgi tahlili N kundan (3 kun) oshgan foydalanuvchilar ID ro'yxatini qaytaradi."""
        if not self.is_connected():
            return []
        try:
            from datetime import timedelta
            threshold = datetime.now(ZoneInfo("Asia/Tashkent")) - timedelta(days=days)
            docs = self._db["brain_frontline.user_dossiers"].find(
                {"analyzed_at": {"$lte": threshold}},
                {"user_id": 1}
            ).sort("analyzed_at", 1).limit(limit)
            return [int(d["user_id"]) for d in docs if d.get("user_id")]
        except Exception as e:
            logger.error("MongoDB get_stale_user_dossier_ids xatolik: %s", e)
            return []

    def get_all_dossier_user_ids(self, limit: int = 2000) -> list[int]:
        """MongoDB'dagi barcha tahlil qilingan foydalanuvchilar ID ro'yxatini qaytaradi."""
        if not self.is_connected():
            return []
        try:
            docs = self._db["brain_frontline.user_dossiers"].find(
                {}, {"user_id": 1}
            ).sort("analyzed_at", 1).limit(limit)
            return [int(d["user_id"]) for d in docs if d.get("user_id")]
        except Exception as e:
            logger.error("MongoDB get_all_dossier_user_ids xatolik: %s", e)
            return []

    def save_pedagogical_outcome(
        self,
        student_id: int,
        topic: str,
        question: str,
        answer_snippet: str,
        outcome: str,
        student_reaction: str = "",
    ) -> bool:
        """Pedagogik natijani MongoDB ga yozadi."""
        if not self.is_connected() or not student_id:
            return False
        try:
            self._db["brain_frontline.pedagogical_outcomes"].insert_one({
                "student_id": student_id,
                "topic": topic,
                "question": question,
                "answer_snippet": answer_snippet,
                "outcome": outcome,
                "student_reaction": student_reaction,
                "timestamp": datetime.now(ZoneInfo("Asia/Tashkent")),
            })
            return True
        except Exception as e:
            logger.error("MongoDB save_pedagogical_outcome xatolik: %s", e)
            return False

    def save_high_yield_pedagogy(self, topic: str, winning_analogy: str) -> bool:
        """Oltin Standart pedagogik analogiyani MongoDB ga yozadi."""
        if not self.is_connected() or not topic:
            return False
        try:
            self._db["brain_frontline.high_yield_pedagogy"].update_one(
                {"topic": topic.strip().lower()},
                {
                    "$set": {
                        "winning_analogy": winning_analogy,
                        "last_updated": datetime.now(ZoneInfo("Asia/Tashkent")),
                    },
                    "$inc": {"success_count": 1},
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_high_yield_pedagogy xatolik: %s", e)
            return False

    def save_bot_pattern(self, bot_username: str, pattern_type: str, observation_summary: str) -> bool:
        """Kuzatilgan bot patternini MongoDB ga yozadi."""
        if not self.is_connected() or not bot_username:
            return False
        try:
            self._db["brain_frontline.bot_interaction_patterns"].insert_one({
                "bot_username": bot_username,
                "pattern_type": pattern_type,
                "observation_summary": observation_summary,
                "created_at": datetime.now(ZoneInfo("Asia/Tashkent")),
            })
            return True
        except Exception as e:
            logger.error("MongoDB save_bot_pattern xatolik: %s", e)
            return False

    # ==========================================
    # 4.7. system_core (Multi-User Obuna Tizimi)
    # ==========================================
    def upsert_user_subscription(self, doc: dict) -> bool:
        """Foydalanuvchi obunasini MongoDB Atlas ga yozadi / yangilaydi."""
        if not self.is_connected() or not doc.get("user_id"):
            return False
        try:
            now = datetime.now(ZoneInfo("Asia/Tashkent"))
            doc_to_save = dict(doc)
            doc_to_save["updated_at"] = now
            self._db["system_core.user_subscriptions"].update_one(
                {"user_id": doc["user_id"]},
                {"$set": doc_to_save, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB upsert_user_subscription xatolik: %s", e)
            return False

    def link_user_group(self, user_id: int, group_id: int) -> bool:
        """Foydalanuvchiga shaxsiy guruh ID sini MongoDB da biriktiradi."""
        if not self.is_connected() or not user_id:
            return False
        try:
            self._db["system_core.user_subscriptions"].update_one(
                {"user_id": user_id},
                {"$set": {"group_id": group_id, "updated_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error("MongoDB link_user_group xatolik: %s", e)
            return False

    def revoke_user_subscription(self, user_id: int) -> bool:
        """Foydalanuvchi obunasini MongoDB da to'xtatadi."""
        if not self.is_connected() or not user_id:
            return False
        try:
            self._db["system_core.user_subscriptions"].update_one(
                {"user_id": user_id},
                {"$set": {"active": 0, "updated_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
            )
            return True
        except Exception as e:
            logger.error("MongoDB revoke_user_subscription xatolik: %s", e)
            return False

    def delete_user_subscription(self, user_id: int) -> bool:
        """Foydalanuvchi obunasini MongoDB dan butunlay o'chiradi."""
        if not self.is_connected() or not user_id:
            return False
        try:
            self._db["system_core.user_subscriptions"].delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error("MongoDB delete_user_subscription xatolik: %s", e)
            return False

    def get_user_subscription(self, user_id: int) -> dict | None:
        """Foydalanuvchi obunasini MongoDB dan oladi."""
        if not self.is_connected() or not user_id:
            return None
        try:
            doc = self._db["system_core.user_subscriptions"].find_one({"user_id": user_id})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            logger.error("MongoDB get_user_subscription xatolik: %s", e)
        return None

    # ==========================================
    # 5. Zero-Loss SQLite <-> MongoDB Synchronization
    # ==========================================
    def restore_to_sqlite(self, sqlite_path: Path) -> dict[str, int]:
        """MongoDB Atlas bulutidagi barcha ma'lumotlarni SQLite bazasiga 100% tiklaydi (Render Auto-Restore)."""
        stats = {
            "settings": 0,
            "learned_insights": 0,
            "students": 0,
            "reminders": 0,
            "daily_plans": 0,
            "saved_locations": 0,
            "ignored_users": 0,
            "precomputed_answers": 0,
            "messages": 0,
            "user_subscriptions": 0,
        }
        if not self.is_connected():
            logger.warning("MongoDB ulanmagan, SQLite'ga tiklash o'tkazib yuborildi.")
            return stats

        try:
            conn = sqlite3.connect(str(sqlite_path))
            cursor = conn.cursor()

            # 1. settings (global_settings)
            try:
                for doc in self._db["system_core.global_settings"].find():
                    k = doc.get("key")
                    v = doc.get("value")
                    if k and v is not None:
                        cursor.execute(
                            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            (k, str(v)),
                        )
                        stats["settings"] += 1
            except Exception as e:
                logger.debug("Restore settings ogohlantirish: %s", e)

            # 2. learned_memory (learned_insights)
            try:
                for doc in self._db["brain_cognitive.learned_insights"].find():
                    topic = doc.get("key") or doc.get("topic") or ""
                    content = doc.get("content") or ""
                    category = doc.get("category") or "rule"
                    source = doc.get("source") or "mentor"
                    created_at = str(doc.get("created_at") or "")
                    updated_at = str(doc.get("updated_at") or "")
                    if topic and content:
                        cursor.execute("SELECT id FROM learned_memory WHERE LOWER(topic) = LOWER(?)", (topic,))
                        ex = cursor.fetchone()
                        if ex:
                            cursor.execute(
                                "UPDATE learned_memory SET content = ?, category = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (content, category, ex[0]),
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO learned_memory (category, topic, content, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (category, topic, content, source, created_at or None, updated_at or None),
                            )
                        stats["learned_insights"] += 1
            except Exception as e:
                logger.debug("Restore learned_memory ogohlantirish: %s", e)

            # 3. students (student_profiles)
            try:
                for doc in self._db["brain_frontline.student_profiles"].find():
                    uid = doc.get("user_id")
                    name = doc.get("full_name") or ""
                    if uid and name:
                        cursor.execute(
                            """
                            INSERT INTO students (user_id, full_name, username, group_name, status, strengths, weaknesses, mentor_notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET
                                full_name = excluded.full_name,
                                username = excluded.username,
                                group_name = excluded.group_name,
                                status = excluded.status,
                                strengths = excluded.strengths,
                                weaknesses = excluded.weaknesses,
                                mentor_notes = excluded.mentor_notes
                            """,
                            (
                                uid,
                                name,
                                doc.get("username", ""),
                                doc.get("group_name", ""),
                                doc.get("status", "yaxshi"),
                                doc.get("strengths", ""),
                                doc.get("weaknesses", ""),
                                doc.get("mentor_notes", ""),
                            ),
                        )
                        stats["students"] += 1
            except Exception as e:
                logger.debug("Restore students ogohlantirish: %s", e)

            # 4. reminders (smart_reminders)
            try:
                now_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
                for doc in self._db["brain_mentor.smart_reminders"].find({"is_sent": False}):
                    cid = doc.get("chat_id")
                    txt = doc.get("text") or doc.get("reminder_text") or ""
                    rat = doc.get("remind_at") or ""
                    crid = doc.get("creator_id", 0)
                    if cid and txt and rat:
                        # Muddati o'tib ketgan eski eslatmalarni qaytadan tiklamaymiz (takroriy spam bo'lmasligi uchun)
                        if rat < now_str:
                            try:
                                self._db["brain_mentor.smart_reminders"].update_one(
                                    {"_id": doc["_id"]},
                                    {"$set": {"is_sent": True, "sent_at": datetime.now(ZoneInfo("Asia/Tashkent"))}},
                                )
                            except Exception:
                                pass
                            continue

                        cursor.execute(
                            "SELECT id FROM reminders WHERE chat_id = ? AND reminder_text = ? AND remind_at = ?",
                            (cid, txt, rat),
                        )
                        ex_row = cursor.fetchone()
                        if not ex_row:
                            cursor.execute(
                                "INSERT INTO reminders (chat_id, creator_id, reminder_text, remind_at, is_sent) VALUES (?, ?, ?, ?, 0)",
                                (cid, crid, txt, rat),
                            )
                            sqlite_id = cursor.lastrowid
                            stats["reminders"] += 1
                        else:
                            sqlite_id = ex_row[0]

                        # MongoDB'da sqlite_id bo'lmasa, yangilab qo'yamiz (kelajakda o'chirish oson bo'lishi uchun)
                        if sqlite_id and not doc.get("sqlite_id"):
                            try:
                                self._db["brain_mentor.smart_reminders"].update_one(
                                    {"_id": doc["_id"]},
                                    {"$set": {"sqlite_id": sqlite_id}},
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.debug("Restore reminders ogohlantirish: %s", e)

            # 5. daily_plans
            try:
                for doc in self._db["brain_mentor.daily_plans"].find():
                    p_date = doc.get("date") or doc.get("plan_date") or ""
                    title = doc.get("title") or ""
                    p_time = doc.get("plan_time") or ""
                    is_c = 1 if doc.get("is_completed") else 0
                    if p_date and title:
                        cursor.execute(
                            "SELECT id FROM daily_plans WHERE plan_date = ? AND title = ?",
                            (p_date, title),
                        )
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO daily_plans (title, plan_date, plan_time, is_completed) VALUES (?, ?, ?, ?)",
                                (title, p_date, p_time, is_c),
                            )
                            stats["daily_plans"] += 1
            except Exception as e:
                logger.debug("Restore daily_plans ogohlantirish: %s", e)

            # 6. saved_locations
            try:
                for doc in self._db["brain_mentor.saved_locations"].find():
                    name = doc.get("name") or ""
                    lat = doc.get("lat") or 0.0
                    lon = doc.get("long") or 0.0
                    details = doc.get("details") or ""
                    if name:
                        cursor.execute("SELECT id FROM saved_locations WHERE LOWER(name_clean) = LOWER(?)", (name,))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO saved_locations (name, name_clean, lat, long, address) VALUES (?, ?, ?, ?, ?)",
                                (doc.get("display_name") or name, name.lower(), lat, lon, details),
                            )
                            stats["saved_locations"] += 1
            except Exception as e:
                logger.debug("Restore saved_locations ogohlantirish: %s", e)

            # 7. ignored_users (security_blacklist)
            try:
                for doc in self._db["system_core.security_blacklist"].find():
                    uid = doc.get("user_id")
                    un = doc.get("username") or ""
                    rsn = doc.get("reason") or ""
                    if uid:
                        cursor.execute(
                            "INSERT OR REPLACE INTO ignored_users (user_id, username, reason) VALUES (?, ?, ?)",
                            (uid, un, rsn),
                        )
                        stats["ignored_users"] += 1
            except Exception as e:
                logger.debug("Restore ignored_users ogohlantirish: %s", e)

            # 8. precomputed_answers
            try:
                for doc in self._db["brain_knowledge.precomputed_answers"].find():
                    top = doc.get("topic") or "Umumiy"
                    q = doc.get("question_pattern") or doc.get("clean_question") or doc.get("trigger_pattern") or ""
                    ans = doc.get("answer_text") or doc.get("response_text") or ""
                    owner_id = int(doc.get("owner_id", 0) or 0)
                    if q and ans:
                        cursor.execute("SELECT id FROM precomputed_answers WHERE question_pattern = ?", (q,))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO precomputed_answers (topic, question_pattern, answer_text, owner_id) VALUES (?, ?, ?, ?)",
                                (top, q, ans, owner_id),
                            )
                            stats["precomputed_answers"] += 1
            except Exception as e:
                logger.debug("Restore precomputed_answers ogohlantirish: %s", e)

            # 9. messages (barcha tahlil qilingan dialoglar va xabarlar)
            try:
                cursor.execute("SELECT COUNT(*) FROM messages")
                existing_msg_count = cursor.fetchone()[0]
                # Agar messages bo'sh bo'lsa yoki to'liq tiklanmagan bo'lsa
                for doc in self._db["brain_frontline.conversations"].find().sort("_id", 1):
                    cid = doc.get("chat_id")
                    role = doc.get("role")
                    cnt = doc.get("content")
                    created_at = doc.get("created_at")
                    if cid and role and cnt:
                        cursor.execute(
                            "SELECT id FROM messages WHERE chat_id = ? AND role = ? AND content = ? LIMIT 1",
                            (cid, role, cnt),
                        )
                        if not cursor.fetchone():
                            if created_at:
                                cursor.execute(
                                    "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                                    (cid, role, cnt, str(created_at)),
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                                    (cid, role, cnt),
                                )
                            stats["messages"] += 1
            except Exception as e:
                logger.debug("Restore messages ogohlantirish: %s", e)

            # 10. mentor_lexicon
            try:
                for doc in self._db["brain_cognitive.mentor_lexicon"].find():
                    term = doc.get("term") or ""
                    meaning = doc.get("meaning") or ""
                    example = doc.get("example") or ""
                    confidence = float(doc.get("confidence", 1.0))
                    if term and meaning:
                        cursor.execute(
                            "INSERT OR REPLACE INTO mentor_lexicon (term, meaning, example, confidence) VALUES (?, ?, ?, ?)",
                            (term, meaning, example, confidence),
                        )
                        stats["mentor_lexicon"] = stats.get("mentor_lexicon", 0) + 1
            except Exception as e:
                logger.debug("Restore mentor_lexicon ogohlantirish: %s", e)

            # 11. self_mistakes (barcha o'rganilgan xatolar va qoidalar)
            try:
                for doc in self._db["brain_cognitive.self_mistakes"].find().sort("created_at", -1):
                    sit = doc.get("situation") or ""
                    mis = doc.get("mistake") or ""
                    cor = doc.get("correction") or ""
                    rul = doc.get("rule") or ""
                    if rul:
                        cursor.execute("SELECT id FROM self_mistakes WHERE rule = ?", (rul,))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO self_mistakes (situation, mistake, correction, rule) VALUES (?, ?, ?, ?)",
                                (sit, mis, cor, rul),
                            )
                            stats["self_mistakes"] = stats.get("self_mistakes", 0) + 1
            except Exception as e:
                logger.debug("Restore self_mistakes ogohlantirish: %s", e)

            # 12. user_dossiers (Miya 5 Shaxsiy Dosyeler)
            try:
                for doc in self._db["brain_frontline.user_dossiers"].find():
                    uid = doc.get("user_id")
                    if uid:
                        cursor.execute(
                            """
                            INSERT INTO user_dossiers (
                                user_id, username, first_name, last_name, phone, bio,
                                channel_username, channel_summary, photo_count, has_stories,
                                dossier_text, common_chats, analyzed_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET
                                username = excluded.username,
                                first_name = excluded.first_name,
                                last_name = excluded.last_name,
                                phone = excluded.phone,
                                bio = excluded.bio,
                                channel_username = excluded.channel_username,
                                channel_summary = excluded.channel_summary,
                                photo_count = excluded.photo_count,
                                has_stories = excluded.has_stories,
                                dossier_text = excluded.dossier_text,
                                common_chats = excluded.common_chats,
                                analyzed_at = excluded.analyzed_at
                            """,
                            (
                                uid,
                                doc.get("username", ""),
                                doc.get("first_name", ""),
                                doc.get("last_name", ""),
                                doc.get("phone", ""),
                                doc.get("bio", ""),
                                doc.get("channel_username", ""),
                                doc.get("channel_summary", ""),
                                doc.get("photo_count", 0),
                                1 if doc.get("has_stories") else 0,
                                doc.get("dossier_text", ""),
                                doc.get("common_chats", ""),
                                str(doc.get("analyzed_at") or ""),
                            ),
                        )
                        stats["user_dossiers"] = stats.get("user_dossiers", 0) + 1
            except Exception as e:
                logger.debug("Restore user_dossiers ogohlantirish: %s", e)

            # 13. high_yield_pedagogy (Oltin Analogiyalar)
            try:
                for doc in self._db["brain_frontline.high_yield_pedagogy"].find():
                    top = doc.get("topic")
                    analogy = doc.get("winning_analogy")
                    sc = doc.get("success_count", 1)
                    if top and analogy:
                        cursor.execute(
                            """
                            INSERT INTO high_yield_pedagogy (topic, winning_analogy, success_count, last_updated)
                            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(topic) DO UPDATE SET
                                winning_analogy = excluded.winning_analogy,
                                success_count = excluded.success_count
                            """,
                            (top, analogy, sc),
                        )
                        stats["high_yield_pedagogy"] = stats.get("high_yield_pedagogy", 0) + 1
            except Exception as e:
                logger.debug("Restore high_yield_pedagogy ogohlantirish: %s", e)

            # 14. bot_interaction_patterns
            try:
                for doc in self._db["brain_frontline.bot_interaction_patterns"].find().limit(200):
                    buname = doc.get("bot_username")
                    ptype = doc.get("pattern_type")
                    obs = doc.get("observation_summary")
                    if buname and obs:
                        cursor.execute(
                            """
                            INSERT INTO bot_interaction_patterns (bot_username, pattern_type, observation_summary)
                            VALUES (?, ?, ?)
                            """,
                            (buname, ptype or "general", obs),
                        )
                        stats["bot_patterns"] = stats.get("bot_patterns", 0) + 1
            except Exception as e:
                logger.debug("Restore bot_patterns ogohlantirish: %s", e)

            # 15. user_subscriptions (Multi-User Obuna Tizimi)
            try:
                for doc in self._db["system_core.user_subscriptions"].find():
                    uid = doc.get("user_id")
                    if uid:
                        cursor.execute(
                            """
                            INSERT INTO user_subscriptions (
                                user_id, username, full_name, phone, business_name,
                                profession, system_prompt, group_id, active, expires_at, role,
                                session_string, session_active,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET
                                username = CASE WHEN excluded.username != '' THEN excluded.username ELSE user_subscriptions.username END,
                                full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE user_subscriptions.full_name END,
                                phone = CASE WHEN excluded.phone != '' THEN excluded.phone ELSE user_subscriptions.phone END,
                                business_name = CASE WHEN excluded.business_name != '' THEN excluded.business_name ELSE user_subscriptions.business_name END,
                                profession = CASE WHEN excluded.profession != '' THEN excluded.profession ELSE user_subscriptions.profession END,
                                system_prompt = CASE WHEN excluded.system_prompt != '' THEN excluded.system_prompt ELSE user_subscriptions.system_prompt END,
                                group_id = CASE WHEN excluded.group_id != 0 THEN excluded.group_id ELSE user_subscriptions.group_id END,
                                active = excluded.active,
                                expires_at = excluded.expires_at,
                                role = excluded.role,
                                session_string = CASE WHEN excluded.session_string != '' THEN excluded.session_string ELSE user_subscriptions.session_string END,
                                session_active = excluded.session_active,
                                updated_at = excluded.updated_at
                            """,
                            (
                                uid,
                                doc.get("username", ""),
                                doc.get("full_name", ""),
                                doc.get("phone", ""),
                                doc.get("business_name", ""),
                                doc.get("profession", ""),
                                doc.get("system_prompt", ""),
                                doc.get("group_id", 0),
                                doc.get("active", 1),
                                str(doc.get("expires_at") or ""),
                                doc.get("role", "client"),
                                doc.get("session_string", ""),
                                int(doc.get("session_active", 0)),
                                str(doc.get("created_at") or ""),
                                str(doc.get("updated_at") or ""),
                            ),
                        )
                        stats["user_subscriptions"] += 1
            except Exception as e:
                logger.warning("⚠️ Restore user_subscriptions xatolik: %s", e)

            conn.commit()
            conn.close()
            logger.info("🧠 [Auto-Restore] MongoDB Atlas -> SQLite tiklanishi yakunlandi: %s", stats)
        except Exception as e:
            logger.error("restore_to_sqlite jarayonida xatolik: %s", e)

        return stats

    def migrate_from_sqlite(self, sqlite_path: Path) -> dict[str, int]:
        """Eski SQLite faylidan barcha ma'lumotlarni 100% yo'qotishlarsiz MongoDB'ga o'tkazadi."""
        stats = {
            "messages": 0,
            "settings": 0,
            "reminders": 0,
            "learned_insights": 0,
            "students": 0,
            "daily_plans": 0,
            "precomputed_answers": 0,
            "user_subscriptions": 0,
        }
        if not self.is_connected() or not sqlite_path.exists():
            logger.warning("Migratsiya bajarilmadi: Mongo ulanmagan yoki SQLite fayli topilmadi: %s", sqlite_path)
            return stats

        try:
            conn = sqlite3.connect(str(sqlite_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. messages -> brain_frontline.conversations
            try:
                cursor.execute("SELECT * FROM messages")
                rows = cursor.fetchall()
                for r in rows:
                    doc = {
                        "chat_id": r["chat_id"],
                        "role": r["role"],
                        "content": r["content"],
                        "sqlite_id": r["id"],
                        "created_at": r["created_at"] if "created_at" in r.keys() else datetime.now(),
                    }
                    self._db["brain_frontline.conversations"].update_one(
                        {"chat_id": r["chat_id"], "content": r["content"], "role": r["role"]},
                        {"$setOnInsert": doc},
                        upsert=True,
                    )
                    stats["messages"] += 1
            except Exception as e_msg:
                logger.warning("Migrate messages ogohlantirish: %s", e_msg)

            # 2. settings -> system_core.global_settings
            try:
                cursor.execute("SELECT * FROM settings")
                for r in cursor.fetchall():
                    self.set_setting(r["key"], r["value"])
                    stats["settings"] += 1
            except Exception as e_st:
                logger.warning("Migrate settings ogohlantirish: %s", e_st)

            # 3. reminders -> brain_mentor.smart_reminders
            try:
                cursor.execute("SELECT * FROM reminders")
                for r in cursor.fetchall():
                    doc = {
                        "chat_id": r["chat_id"],
                        "creator_id": r["creator_id"],
                        "text": r["reminder_text"],
                        "remind_at": r["remind_at"],
                        "is_sent": bool(r["is_sent"]),
                        "sqlite_id": r["id"],
                    }
                    self._db["brain_mentor.smart_reminders"].update_one(
                        {"chat_id": r["chat_id"], "text": r["reminder_text"], "remind_at": r["remind_at"]},
                        {"$setOnInsert": doc},
                        upsert=True,
                    )
                    stats["reminders"] += 1
            except Exception as e_rem:
                logger.warning("Migrate reminders ogohlantirish: %s", e_rem)

            # 4. learned_memory -> brain_cognitive.learned_insights
            try:
                cursor.execute("SELECT * FROM learned_memory")
                for r in cursor.fetchall():
                    r_keys = r.keys()
                    k = r["topic"] if "topic" in r_keys else (r["key"] if "key" in r_keys else str(r["id"]))
                    cat = r["category"] if "category" in r_keys else "general"
                    src = r["source"] if "source" in r_keys else "chat"
                    conf = float(r["confidence"]) if "confidence" in r_keys and r["confidence"] else 1.0
                    self.save_learned_insight(
                        key=k,
                        content=r["content"],
                        category=cat,
                        confidence=conf,
                        source=src,
                    )
                    stats["learned_insights"] += 1
            except Exception as e_lm:
                logger.warning("Migrate learned_memory ogohlantirish: %s", e_lm)

            # 5. students -> brain_frontline.student_profiles
            try:
                cursor.execute("SELECT * FROM students")
                for r in cursor.fetchall():
                    doc = {
                        "user_id": r["user_id"],
                        "full_name": r["full_name"],
                        "username": r["username"] if "username" in r.keys() else "",
                        "group_name": r["group_name"] if "group_name" in r.keys() else "",
                        "questions_count": r["questions_count"] if "questions_count" in r.keys() else 0,
                        "strengths": r["strengths"] if "strengths" in r.keys() else "",
                        "weaknesses": r["weaknesses"] if "weaknesses" in r.keys() else "",
                        "mentor_notes": r["mentor_notes"] if "mentor_notes" in r.keys() else "",
                    }
                    self._db["brain_frontline.student_profiles"].update_one(
                        {"user_id": r["user_id"]},
                        {"$set": doc},
                        upsert=True,
                    )
                    stats["students"] += 1
            except Exception as e_std:
                logger.warning("Migrate students ogohlantirish: %s", e_std)

            # 6. daily_plans -> brain_mentor.daily_plans
            try:
                cursor.execute("SELECT * FROM daily_plans")
                for r in cursor.fetchall():
                    doc = {
                        "date": r["plan_date"] if "plan_date" in r.keys() else r["date"],
                        "title": r["title"],
                        "plan_time": r["plan_time"] if "plan_time" in r.keys() else "",
                        "is_completed": bool(r["is_completed"]),
                    }
                    self._db["brain_mentor.daily_plans"].update_one(
                        {"title": r["title"], "date": doc["date"]},
                        {"$setOnInsert": doc},
                        upsert=True,
                    )
                    stats["daily_plans"] += 1
            except Exception as e_dp:
                logger.warning("Migrate daily_plans ogohlantirish: %s", e_dp)

            # 7. precomputed_answers -> brain_knowledge.precomputed_answers
            try:
                cursor.execute("SELECT * FROM precomputed_answers")
                for r in cursor.fetchall():
                    r_keys = r.keys()
                    topic = r["topic"] if "topic" in r_keys else ""
                    q_pat = r["question_pattern"] if "question_pattern" in r_keys else r.get("clean_question", "")
                    ans = r["answer_text"] if "answer_text" in r_keys else r.get("response_text", "")
                    cat = r["category"] if "category" in r_keys else "dasturlash"
                    doc = {
                        "topic": topic,
                        "category": cat,
                        "trigger_pattern": q_pat,
                        "clean_question": q_pat,
                        "response_text": ans,
                        "usage_count": r["usage_count"] if "usage_count" in r_keys else 0,
                    }
                    self._db["brain_knowledge.precomputed_answers"].update_one(
                        {"clean_question": q_pat},
                        {"$set": doc},
                        upsert=True,
                    )
                    stats["precomputed_answers"] += 1
            except Exception as e_pa:
                logger.warning("Migrate precomputed_answers ogohlantirish: %s", e_pa)

            # 8. user_subscriptions -> system_core.user_subscriptions
            try:
                cursor.execute("SELECT * FROM user_subscriptions")
                for r in cursor.fetchall():
                    r_keys = r.keys()
                    doc = {
                        "user_id": r["user_id"],
                        "username": r["username"] if "username" in r_keys else "",
                        "full_name": r["full_name"] if "full_name" in r_keys else "",
                        "phone": r["phone"] if "phone" in r_keys else "",
                        "business_name": r["business_name"] if "business_name" in r_keys else "",
                        "profession": r["profession"] if "profession" in r_keys else "",
                        "system_prompt": r["system_prompt"] if "system_prompt" in r_keys else "",
                        "group_id": r["group_id"] if "group_id" in r_keys else 0,
                        "active": r["active"] if "active" in r_keys else 1,
                        "expires_at": str(r["expires_at"]) if "expires_at" in r_keys and r["expires_at"] else "",
                        "role": r["role"] if "role" in r_keys else "client",
                        "session_string": r["session_string"] if "session_string" in r_keys and r["session_string"] else "",
                        "session_active": r["session_active"] if "session_active" in r_keys and r["session_active"] else 0,
                        "created_at": str(r["created_at"]) if "created_at" in r_keys and r["created_at"] else "",
                        "updated_at": str(r["updated_at"]) if "updated_at" in r_keys and r["updated_at"] else "",
                    }
                    self._db["system_core.user_subscriptions"].update_one(
                        {"user_id": r["user_id"]},
                        {"$set": doc},
                        upsert=True,
                    )
                    stats["user_subscriptions"] += 1
            except Exception as e_sub:
                logger.warning("Migrate user_subscriptions ogohlantirish: %s", e_sub)

            conn.close()
            logger.info("🎉 SQLite -> MongoDB Atlas migratsiyasi 100% muvaffaqiyatli: %s", stats)
        except Exception as e:
            logger.error("Migratsiya jarayonida xatolik: %s", e)

        return stats


# Global bitta instansiya
mongo_memory_service = MongoMemoryService()
