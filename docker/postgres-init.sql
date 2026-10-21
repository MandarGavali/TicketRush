-- Runs once, the first time the Postgres volume is created.
-- The main database (ticketrush) is created by POSTGRES_DB; this adds one for the tests.
CREATE DATABASE ticketrush_test OWNER ticketrush;
