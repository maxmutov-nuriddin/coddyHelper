with open("/Applications/Project/coddyHelper/templates/admin_app.html", "r") as f:
    content = f.read()

content = content.replace("'Noma'lum xato'", "\"Noma'lum xato\"")

with open("/Applications/Project/coddyHelper/templates/admin_app.html", "w") as f:
    f.write(content)
