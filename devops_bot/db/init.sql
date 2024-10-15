CREATE ROLE repl_user WITH REPLICATION PASSWORD '123' LOGIN;

-- Создание базы данных
CREATE DATABASE db_customers;

-- Переключение на созданную базу данных
\connect db_customers;

-- Создание таблицы для номеров телефонов
CREATE TABLE IF NOT EXISTS phone_numbers (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL
);

-- Создание таблицы для users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL
);

-- Вставка данных в таблицу users
INSERT INTO users (email) 
VALUES ('test1@example.com'), ('test2@example2.eu');

-- Вставка данных в таблицу phone_numbers
INSERT INTO phone_numbers (phone_number) 
VALUES ('87777777777'), ('+71231231212');

