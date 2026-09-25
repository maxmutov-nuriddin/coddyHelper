with open("/Applications/Project/coddyHelper/templates/admin_app.html", "r") as f:
    content = f.read()

replacement = """
      const codeModeSelect = document.getElementById("select-ai-code-mode");
      if (codeModeSelect) {
        if (isSuper) {
          codeModeSelect.innerHTML = `
            <option value="full_code">💻 To'liq ishlaydigan kod variantini taqdim etish</option>
            <option value="hints_only">💡 Faqat maslahat va yo'nalish (Tayyor kod bermaslik)</option>
          `;
          codeModeSelect.previousElementSibling.innerText = "💻 Kod Berish Darajasi";
        } else {
          codeModeSelect.innerHTML = `
            <option value="full_code">💻 To'liq ishlaydigan kod tayyorlab berish</option>
            <option value="snippets_only">📝 Faqat qisqa qismlar (Snippetlar)</option>
            <option value="hints_only">💡 Faqat tushuntirish va yo'nalish berish</option>
          `;
          codeModeSelect.previousElementSibling.innerText = "💻 Kod Yozish Yordami";
        }
        if (data.ai_code_mode) codeModeSelect.value = data.ai_code_mode;
      }
      
      const inputGroupId = document.getElementById("input-my-group-id");
      if (inputGroupId && data.current_group_id) {
          inputGroupId.value = data.current_group_id !== 0 ? data.current_group_id : "";
      }
"""
content = content.replace('      const codeModeSelect = document.getElementById("select-ai-code-mode");\n      if (codeModeSelect) {\n        if (isSuper) {\n          codeModeSelect.innerHTML = `\n            <option value="full_code">💻 To\'liq ishlaydigan kod variantini taqdim etish</option>\n            <option value="hints_only">💡 Faqat maslahat va yo\'nalish (Tayyor kod bermaslik)</option>\n          `;\n          codeModeSelect.previousElementSibling.innerText = "💻 Kod Berish Darajasi";\n        } else {\n          codeModeSelect.innerHTML = `\n            <option value="full_code">💻 To\'liq ishlaydigan kod tayyorlab berish</option>\n            <option value="snippets_only">📝 Faqat qisqa qismlar (Snippetlar)</option>\n            <option value="hints_only">💡 Faqat tushuntirish va yo\'nalish berish</option>\n          `;\n          codeModeSelect.previousElementSibling.innerText = "💻 Kod Yozish Yordami";\n        }\n        if (data.ai_code_mode) codeModeSelect.value = data.ai_code_mode;\n      }', replacement)

with open("/Applications/Project/coddyHelper/templates/admin_app.html", "w") as f:
    f.write(content)
print("Populated")
