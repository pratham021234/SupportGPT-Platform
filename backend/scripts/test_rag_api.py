import httpx
import json

BASE_URL = "http://127.0.0.1:8000"
ACME_ORG_ID = "b4c03998-1c48-421e-8cba-526179517f20"

def test_rag():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login
        login_res = client.post("/api/v1/auth/login", json={
            "email": "admin@acme.com",
            "password": "Password123!"
        })
        print(f"Login status: {login_res.status_code}")
        assert login_res.status_code == 200, login_res.text

        # 2. Search knowledge
        search_res = client.post(
            f"/api/v1/organizations/{ACME_ORG_ID}/knowledge/search",
            json={
                "query": "refund policy",
                "top_k": 5,
                "enable_hybrid": True
            }
        )
        print(f"Search status: {search_res.status_code}")
        print("Search response:", json.dumps(search_res.json(), indent=2))

        # 3. Answer question
        answer_res = client.post(
            f"/api/v1/organizations/{ACME_ORG_ID}/knowledge/answer",
            json={
                "question": "What is the refund window for software licenses?",
                "top_k": 5,
                "enable_hybrid": True
            }
        )
        print(f"Answer status: {answer_res.status_code}")
        print("Answer response:", json.dumps(answer_res.json(), indent=2))

        # 4. Unanswerable question (abstention test)
        abstain_res = client.post(
            f"/api/v1/organizations/{ACME_ORG_ID}/knowledge/answer",
            json={
                "question": "How do I bake sourdough bread?",
                "top_k": 5,
                "enable_hybrid": True
            }
        )
        print(f"Abstain status: {abstain_res.status_code}")
        print("Abstain response:", json.dumps(abstain_res.json(), indent=2))

if __name__ == "__main__":
    test_rag()
