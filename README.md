# Orbata Core

Orbata Core is a lightweight authentication and OTP verification engine.

## 🚀 Features

- Email OTP generation & verification
- Redis-based TTL storage
- Rate limiting
- Attempt protection
- Docker-based architecture

---

## 🏗️ Architecture

Client -> Core API -> Redis -> (Queue -> Email Service)

---

## ⚙️ Run Locally

```bash
docker compose up --build
```

Core runs on:  
`http://localhost:8101`

## 📡 API

### Send OTP

`POST /otp/send`

Params:

- `email`

### Verify OTP

`POST /otp/verify`

Params:

- `email`
- `otp`

## 🔐 Security

- OTP hashed
- TTL (5 minutes)
- Max attempts
- Rate limiting

## 🧪 Testing

Use curl or Postman:

```bash
curl -X POST "http://localhost:8101/otp/send?email=test@test.com"
```
