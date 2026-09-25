with open("/Applications/Project/coddyHelper/templates/admin_app.html", "r") as f:
    content = f.read()

replacement = """
      const dashGroupId = document.getElementById("dashboard-widget-group-id");
      if (dashGroupId) dashGroupId.style.display = isSuper ? "none" : "block";

      // Tab-Knowledge Customization for Client vs Super Admin
"""
content = content.replace("      // Tab-Knowledge Customization for Client vs Super Admin", replacement)

with open("/Applications/Project/coddyHelper/templates/admin_app.html", "w") as f:
    f.write(content)
print("Updated")
