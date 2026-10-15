import mysql.connector

def get_mysql_connection():
    mydb = mysql.connector.connect(host="dev-hekmadb.cyjz2t0etrbb.us-east-1.rds.amazonaws.com", user="root",
                                   passwd="admin724#", database="operations")
    return mydb