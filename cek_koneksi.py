import mysql.connector

try:
    mydb = mysql.connector.connect(
      host="localhost",
      user="root",
      password="",     # Kosongkan jika default XAMPP
      database="nusa_niaga"
    )
    print("✅ BERHASIL! Koneksi ke database nusa_niaga sukses.")
    
    mycursor = mydb.cursor()
    mycursor.execute("SHOW TABLES")
    
    print("Daftar Tabel yang ditemukan:")
    for x in mycursor:
      print(f"- {x}")

except Exception as e:
    print("❌ GAGAL! Python tidak bisa masuk ke database.")
    print(f"Penyebab: {e}")