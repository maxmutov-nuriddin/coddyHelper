"""
Jarayon darajasidagi umumiy obyektlar registri (circular import'siz).
main.py ishga tushganda to'ldiradi; boshqa servislar (masalan bot) shu yerdan oladi.
"""

main_client = None  # Super Admin (@mentor_cc) Telethon clienti
