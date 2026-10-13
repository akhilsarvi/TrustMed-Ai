# 🐳 Docker Setup for TrustMed AI

This directory contains containerization files for building and running **TrustMed AI** with Docker & Docker Compose.

---

## 🚀 Quick Start with Docker Compose

To launch both the **TrustMed AI Web Application** and **Neo4j Graph Database**:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Access services at:
* **TrustMed AI Web Interface**: [http://localhost:5001](http://localhost:5001)
* **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)

---

## 🛠️ Build Docker Image Directly

```bash
docker build -t trustmed-ai -f docker/Dockerfile .
docker run -p 5001:5001 --env-file .env trustmed-ai
```
