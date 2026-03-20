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

## v0.2 - Async OTP Delivery

Orbata Core now supports asynchronous OTP delivery using a Redis-based queue and a dedicated email worker.

### Flow

Client -> Core API -> Redis Queue -> Email Worker -> SMTP -> Inbox

### Features

- Non-blocking OTP generation
- Scalable worker-based delivery
- Real email sending via Brevo SMTP
- Verified domain (DKIM + DMARC)

### Environment Variables

Create a `.env` file:

```env
SMTP_SERVER=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_LOGIN=your_smtp_login
SMTP_PASSWORD=your_smtp_key
FROM_EMAIL=no-reply@yourdomain.com
```

⚠️ Keep SMTP credentials private and never commit `.env` to version control.

## v0.3 - Reliability Layer

Orbata Core now includes a reliability layer to improve delivery guarantees for asynchronous OTP email processing.

### Architecture

Core -> Queue -> Worker -> Retry -> DLQ

### Reliability Capabilities

- Retry system with exponential backoff to reduce transient SMTP or network failures.
- Dead-letter queue (DLQ) handling for jobs that exceed max retry attempts.
- Fault-tolerant email delivery flow with controlled reprocessing and failure isolation.

### Redis Queues

- `email_queue`: primary queue for new OTP delivery jobs.
- `email_retry_queue`: retry queue for delayed reprocessing attempts.
- `email_dlq`: dead-letter queue for permanently failed jobs.
