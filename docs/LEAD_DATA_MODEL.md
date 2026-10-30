# LEAD DATA MODEL

## Lead

```json
{
  "id": "LEAD-YYYY-XXXXXX",
  "business": {
    "name": "",
    "category": "",
    "city": "",
    "neighborhood": "",
    "address": "",
    "website": "",
    "website_status": "UNKNOWN"
  },
  "contacts": [
    {
      "name": "",
      "role": "",
      "phone": "",
      "type": "BUSINESS",
      "confidence": "UNKNOWN",
      "evidence_ids": []
    }
  ],
  "digital_presence": {
    "instagram": "",
    "facebook": "",
    "google_maps": "",
    "other": []
  },
  "opportunity": {
    "classification": "UNCERTAIN",
    "evidence": [],
    "hypothesis": "",
    "uncertainties": []
  },
  "outreach": {
    "recommended_contact_id": "",
    "opening_message": "",
    "human_review": true
  },
  "sources": [],
  "pipeline_status": "NEW",
  "discovered_at": "",
  "updated_at": ""
}
```

## Source

```json
{
  "id": "SRC-XXXXXX",
  "url": "",
  "title": "",
  "source_type": "E1",
  "accessed_at": "",
  "supports": []
}
```

## Conversation

```json
{
  "lead_id": "",
  "timestamp": "",
  "direction": "INBOUND",
  "text": "",
  "intent": "UNKNOWN",
  "notes": ""
}
```
