# -*- coding: utf-8 -*-

import sqlite3


class DatabaseController:

    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.cursor = self.connection.cursor()

    def close(self):
        self.connection.close()

    def create_new_user(self, chat_id):
        sql_query = "SELECT * FROM Users WHERE chat_id == ?"
        sql_data = (chat_id,)
        self.cursor.execute(sql_query, sql_data)
        if self.cursor.fetchone() is None:
            sql_query = "INSERT INTO Users (chat_id, state) VALUES (?, ?)"
            sql_data = (chat_id, 0)
        else:
            sql_query = "UPDATE Users SET state = ? WHERE chat_id = ?"
            sql_data = (0, chat_id)
        self.cursor.execute(sql_query, sql_data)
        self.connection.commit()

