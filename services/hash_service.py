import hashlib, json

class HashService:
    @staticmethod
    def canonical_json(data: dict) -> str:
        """Convert a dictionary to a canonical JSON string."""
        return json.dumps(data, sort_keys=True, separators=(',', ':'))
    
    @staticmethod
    def compute_hash(tenant_id, subject_id, event_type, event_time, payload, previous_hash):
        base = "|".join([
            tenant_id,
            subject_id,
            event_type,
            event_time.isoformat(),
            HashService.canonical_json(payload),
            previous_hash or "GENESIS"
        ])
        return hashlib.sha256(base.encode()).hexdigest()