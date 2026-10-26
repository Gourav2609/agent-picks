"""Hand-written category lists. A package is in a category only if it is named here.

Names are matched exactly (npm names as written, PyPI names normalised to lower case
with '-' for '_'/'.'). An npm entry ending in '/*' matches every package in that scope.
"""

NPM = {
    "auth": [
        "next-auth", "@auth/*", "better-auth", "@better-auth/*", "@clerk/*", "lucia", "@lucia-auth/*",
        "@workos-inc/*", "@kinde-oss/*", "@stytch/*", "stytch", "auth0", "@auth0/*",
        "supertokens-node", "supertokens-auth-react", "supertokens-web-js", "@supabase/auth-helpers-nextjs",
        "@supabase/auth-helpers-react", "@supabase/auth-ui-react", "@supabase/ssr", "@supabase/auth-js", "firebase-auth",
        "passport", "passport-local", "passport-jwt", "passport-google-oauth20", "passport-github2",
        "jsonwebtoken", "jose", "jwt-decode", "bcrypt", "bcryptjs", "argon2", "@node-rs/argon2", "@node-rs/bcrypt", "oslo", "@oslojs/*", "arctic",
        "@simplewebauthn/*", "otplib", "speakeasy", "iron-session", "express-session", "@descope/*",
        "@logto/*", "@propelauth/*", "@hono/oauth-providers", "@hono/auth-js", "@fastify/jwt",
        "@nestjs/jwt", "@nestjs/passport", "keycloak-js", "oidc-client-ts", "openid-client",
        "@azure/msal-browser", "@azure/msal-node", "@azure/msal-react", "@react-oauth/google",
        "google-auth-library", "@privy-io/*", "@dynamic-labs/*", "@stackframe/*", "@convex-dev/auth",
        "@frontegg/*", "@ory/*", "@hanko/*", "@corbado/*", 
    ],
    "email": [
        "resend", "@react-email/*", "react-email", "nodemailer", "@sendgrid/mail",
        "@sendgrid/client", "postmark", "mailgun.js", "mailgun-js", "@aws-sdk/client-ses",
        "@aws-sdk/client-sesv2", "@mailchimp/mailchimp_transactional", "@mailchimp/mailchimp_marketing",
        "@emailjs/browser", "emailjs", "@emailjs/nodejs", "@getbrevo/brevo", "sib-api-v3-sdk", "brevo",
        "loops", "@plunk/node", "mjml", "email-templates", "@sendinblue/client",
        "mailersend", "@mailtrap/*", "mailtrap", "node-mailjet", "@azure/communication-email",
        "@jsx-email/*", "jsx-email",
        "maizzle", "@maizzle/*", "imapflow", "smtp-server", "@payloadcms/email-nodemailer", "mailparser", 
    ],
    "database/ORM": [
        "prisma", "@prisma/client", "@prisma/*", "drizzle-orm", "drizzle-kit", "drizzle-zod", "typeorm",
        "sequelize", "mongoose", "mongodb", "pg", "postgres", "mysql2", "mysql",
        "better-sqlite3", "sqlite3", "sqlite", "@libsql/client", "@neondatabase/serverless",
        "@planetscale/database", "kysely", "knex", "@supabase/supabase-js", "@supabase/postgrest-js", "supabase", "expo-sqlite", "redis", "ioredis",
        "@upstash/redis", "@vercel/postgres", "@vercel/kv", "@electric-sql/pglite", "convex",
        "@tursodatabase/*", "@mikro-orm/*", "objection", "@neondatabase/*", "@google-cloud/firestore", "@aws-sdk/client-dynamodb", "@aws-sdk/lib-dynamodb", "dynamoose",
        "@pinecone-database/pinecone", "@qdrant/js-client-rest", "chromadb", "pgvector",
        "@cloudflare/d1", "@zenstackhq/*", "@instantdb/*", "dexie", "idb", "idb-keyval",
        "@electric-sql/*", "@triplit/*", "@rocicorp/zero", "pocketbase", "@surrealdb/*", "surrealdb",
        "@clickhouse/client", "duckdb", "@duckdb/*", "sql.js", "@lancedb/lancedb", "lowdb",
        "postgres-migrations", "node-pg-migrate", "umzug", "@databases/*",
    ],
    "payments": [
        "stripe", "@stripe/stripe-js", "@stripe/react-stripe-js", "@stripe/*", "@lemonsqueezy/lemonsqueezy.js",
        "@paddle/paddle-js", "@paddle/paddle-node-sdk", "@paddle/*", "razorpay", "@polar-sh/*",
        "@paypal/react-paypal-js", "@paypal/checkout-server-sdk", "@paypal/paypal-js", "@paypal/*",
        "braintree", "square", "@square/*", "dodopayments", "@dodopayments/*", "@revenuecat/*",
        "react-native-purchases", "react-native-purchases-ui", "@mollie/api-client", "chargebee",
        "@creem_io/*", "creem", "@whop/*", "@adyen/*", "@chargebee/*", "@coinbase/commerce",
        "cashfree-pg", "@cashfreepayments/*", "autumn-js", "@flowglad/*",
        "react-native-iap", "expo-in-app-purchases", "@x402/*", "x402", "x402-next", "x402-express",
    ],
}

PYPI = {
    "auth": [
        "pyjwt", "python-jose", "passlib", "bcrypt", "argon2-cffi", "authlib", "fastapi-users",
        "django-allauth", "flask-login", "flask-jwt-extended", "djangorestframework-simplejwt",
        "python-keycloak", "msal", "google-auth", "google-auth-oauthlib", "itsdangerous",
        "pyotp", "clerk-backend-api", "supabase-auth", "gotrue", "workos", "auth0-python",
        "pwdlib", "joserfc", "oauthlib", "requests-oauthlib", "social-auth-app-django",
        "stytch", "webauthn", 
    ],
    "email": [
        "sendgrid", "resend", "postmarker", "aiosmtplib", "fastapi-mail", "emails", "flask-mail",
        "mailgun", "django-anymail", "mailjet-rest", "brevo-python", "sib-api-v3-sdk",
        "yagmail", "imapclient", "mailtrap", "postmark",
    ],
    "database/ORM": [
        "sqlalchemy", "psycopg2", "psycopg2-binary", "psycopg", "psycopg-binary", "psycopg-pool",
        "asyncpg", "alembic", "pymongo", "motor", "redis", "sqlmodel", "tortoise-orm", "peewee",
        "aiosqlite", "prisma", "supabase", "pymysql", "aiomysql", "mysqlclient", "databases",
        "beanie", "odmantic", "mongoengine", "duckdb", "libsql-client", "libsql-experimental",
        "pgvector", "chromadb", "qdrant-client", "pinecone", "pinecone-client", "lancedb",
        "clickhouse-connect", "google-cloud-firestore", "neo4j", "elasticsearch",
        "sqlite-utils", "piccolo", "ormar", "edgedb", "gel", "surrealdb", "weaviate-client",
        "pymilvus", "oracledb", "pyodbc", "snowflake-connector-python", "google-cloud-bigquery",
        "flask-sqlalchemy", "flask-migrate", "dj-database-url", "sqlite-vec", "aioredis",
        "valkey", "upstash-redis", "lancedb", 
    ],
    "payments": [
        "stripe", "razorpay", "paypalrestsdk", "paypal-server-sdk", "polar-sdk", "braintree",
        "squareup", "dj-stripe", "paddle-python-sdk", "lemonsqueezy", "mollie-api-python",
        "dodopayments", "chargebee", "cashfree-pg", "adyen", "revenuecat", "x402",
    ],
}

# Words that suggest an uncategorised package might belong somewhere; used only to print
# a review list, never to assign a category.
REVIEW_HINTS = ["auth", "jwt", "oauth", "session", "login", "passkey", "mail", "smtp", "pay", "billing",
                "checkout", "subscri", "sql", "orm", "db", "database", "mongo", "redis", "postgres",
                "supabase", "firebase", "vector"]


def _match(name, patterns):
    for p in patterns:
        if p.endswith("/*"):
            if name.startswith(p[:-1]):
                return True
        elif name == p:
            return True
    return False


def category(ecosystem, name):
    table = NPM if ecosystem == "npm" else PYPI
    for cat, pats in table.items():
        if _match(name, pats):
            return cat
    return None
