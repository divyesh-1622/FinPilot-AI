# FinPilot AI 🚀

**AI-powered Personal CFO** that connects to PayPal transactions, tracks recurring subscriptions, forecasts monthly savings, and surfaces legal tax-saving strategies.

Built for the **PayPal AI Hackathon** using **FastAPI**, **Next.js**, **AG Grid**, **Zapier**, **Render**, and **Postman**.

---

## ✨ Key Features

- **PayPal Transaction Sync:** Connects via OAuth 2.0 to ingest and categorize PayPal Sandbox and live transaction records into a unified ledger.
- **Interactive Smart Ledger (AG Grid):** Sort, filter, and inline-edit transactions—double-click any transaction to toggle **Tax Deductible** flags and see KPI metrics recalculate in real time.
- **AI Financial Health & Forecasting:** Evaluates spending patterns, calculates a dynamic Financial Health Score, detects recurring subscriptions, and projects monthly savings.
- **Conversational AI CFO:** Natural-language financial assistant capable of answering questions about cash flow, subscription waste, and deduction opportunities.
- **Automated Alerts (Zapier Integration):** Triggers real-time webhook alerts for unusual spending, upcoming renewals, or savings milestones.
- **Legal Tax Optimization Engine:** Identifies eligible business and personal tax deductions directly from categorized transaction history.

---

## 🛠️ Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js, React, TypeScript, Tailwind CSS, AG Grid |
| **Backend** | Python, FastAPI, Uvicorn, Pydantic, SQLite (`finpilot.db`) |
| **Integrations** | PayPal REST API (OAuth 2.0), OpenAI API, Zapier Webhooks |
| **Deployment & Testing** | Render (`render.yaml`), Postman (`FinPilot_AI.postman_collection.json`) |

---

## 📁 Project Structure

```text
FinPilot-AI/
├── backend/
│   ├── main.py                              # FastAPI application & PayPal/AI endpoints
│   ├── finpilot.db                          # SQLite database
│   └── render.yaml                          # Render deployment blueprint
├── frontend/
│   ├── src/app/                             # Next.js App Router pages (Dashboard & Login)
│   ├── lib/api.ts                           # Backend API client
│   └── package.json                         # Frontend dependencies (Next.js, AG Grid)
├── postman/
│   └── FinPilot_AI.postman_collection.json  # Ready-to-import API test collection
├── LICENSE                                  # MIT License
└── README.md
```

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
