with open("/Applications/Project/coddyHelper/templates/admin_app.html", "r") as f:
    content = f.read()

widget_html = """
        <!-- USER GROUP ID CONFIGURATION -->
        <div id="dashboard-widget-group-id" style="background: rgba(34, 197, 94, 0.05); border: 1px solid rgba(34, 197, 94, 0.28); border-radius: 10px; padding: 12px 14px; margin-top: 12px; display: none;">
          <div style="font-size: 13px; font-weight: 700; color: #22c55e; display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
            <span>👥</span> Shaxsiy Guruh ID'ni sozlash
          </div>
          <div style="font-size: 11px; color: var(--hint-color); margin-bottom: 10px;">
            Agent faqat shu guruhdagi savollarga e'tibor qaratadi va shu guruhga ishlaydi. Manfiy ishorali ID kiriting (masalan: -100123456789).
          </div>
          <div style="display: flex; gap: 8px;">
            <input type="text" id="input-my-group-id" placeholder="-100..." class="form-input" style="flex: 1; padding: 6px 10px; font-size: 13px; background: rgba(0,0,0,0.3); border: 1px solid rgba(34, 197, 94, 0.3);">
            <button onclick="saveMyGroupId()" class="btn-primary" style="padding: 6px 14px; border-radius: 6px; font-size: 12px;">Saqlash</button>
          </div>
        </div>
"""

js_code = """
    async function saveMyGroupId() {
      const val = document.getElementById('input-my-group-id').value.trim();
      if (!val) { showToast('ID kiriting', true); return; }
      haptic();
      try {
        const res = await apiRequest('/api/update-group-id', 'POST', { group_id: parseInt(val) });
        if (res && res.ok) {
          showToast('Guruh ID muvaffaqiyatli saqlandi ✅');
        } else {
          showToast('Xatolik: ' + (res?.error || 'Noma\'lum xato'), true);
        }
      } catch (e) {
        showToast('Tizim xatosi', true);
      }
    }
"""

content = content.replace('        <!-- GEMINI CONTROL HUB -->', widget_html + '\n        <!-- GEMINI CONTROL HUB -->')
content = content.replace('    // ==================== PWA & INSTALL SUPPORT ====================', js_code + '\n    // ==================== PWA & INSTALL SUPPORT ====================')

with open("/Applications/Project/coddyHelper/templates/admin_app.html", "w") as f:
    f.write(content)

print("Widget added")
