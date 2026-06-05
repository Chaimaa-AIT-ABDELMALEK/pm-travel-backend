import pymysql

conn = pymysql.connect(
    host='localhost',
    port=3306,
    user='root',
    password='root',
    database='pm_travel'
)
cur = conn.cursor()
cur.execute("UPDATE prospects SET statut='nouveau', email_valide=1 WHERE email='zakiaazizi17@gmail.com'")
conn.commit()
print('OK - lignes modifiées:', cur.rowcount)
conn.close()