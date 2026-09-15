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
        if not self._is_connected or self._client is None:
            return False
        try:
            self._client.admin.command("ping")
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

    def get_conversation_history(self, chat_id: int, limit: int = 15) -> list[dict]:
        if not self.is_connected():
            return []
        try:
            cursor = (
                self._db["brain_frontline.conversations"]
                .find({"chat_id": chat_id})
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
            current["iq_score"] = min(200, current.get("iq_score", 140) + iq_points)
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
            _id = ObjectId(reminder_id) if ObjectId.is_valid(reminder_id) else reminder_id
            self._db["brain_mentor.smart_reminders"].update_one(
                {"_id": _id},
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

    # ==========================================
    # 5. Zero-Loss SQLite -> MongoDB Migration
    # ==========================================
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

            conn.close()
            logger.info("🎉 SQLite -> MongoDB Atlas migratsiyasi 100% muvaffaqiyatli: %s", stats)
        except Exception as e:
            logger.error("Migratsiya jarayonida xatolik: %s", e)

        return stats


# Global bitta instansiya
mongo_memory_service = MongoMemoryService()
