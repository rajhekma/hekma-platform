import re
import random
import string
from typing import Protocol, Optional
from faker import Faker

from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy
from api.models.token_mapping import TokenMapping
from datetime import datetime

fake = Faker()


class AnonymizerStrategy(Protocol):
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str: ...


class RedactStrategy:
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        if policy.custom_replacement:
            return policy.custom_replacement

        et = entity_type.upper()
        if et in ("SSN", "US_SSN"):
            return re.sub(r'\d', 'X', original)
        if et in ("PHONE", "PHONE_NUMBER", "US_PHONE"):
            return re.sub(r'\d', 'X', original)
        if et in ("CREDIT_CARD", "CREDIT_CARD_NUMBER"):
            return re.sub(r'\d', 'X', original)
        if et in ("EMAIL", "EMAIL_ADDRESS"):
            return "XXX@XXX.XXX"
        if et in ("IP_ADDRESS", "IP"):
            return "XXX.XXX.XXX.XXX"
        return "X" * len(original)


class RandomizedStrategy:
    GENERATORS = {
        "PERSON": lambda: fake.name(),
        "EMAIL": lambda: fake.email(),
        "PHONE": lambda: fake.phone_number(),
        "PHONE_NUMBER": lambda: fake.phone_number(),
        "SSN": lambda: f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
        "US_SSN": lambda: f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
        "DATE": lambda: fake.date(),
        "ADDRESS": lambda: fake.street_address(),
        "CREDIT_CARD": lambda: fake.credit_card_number(),
        "CREDIT_CARD_NUMBER": lambda: fake.credit_card_number(),
        "DRIVER_LICENSE": lambda: fake.bothify(text='??#######'),
        "US_DRIVER_LICENSE": lambda: fake.bothify(text='??#######'),
        "PASSPORT": lambda: fake.bothify(text='??#######'),
        "US_PASSPORT": lambda: fake.bothify(text='??#######'),
        "IP_ADDRESS": lambda: fake.ipv4(),
    }

    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        gen = self.GENERATORS.get(entity_type.upper())
        if gen:
            return gen()
        return ''.join(random.choices(string.ascii_letters + string.digits, k=len(original)))


class AlternateStrategy:
    def __init__(self):
        self._cache: dict[str, str] = {}

    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        if original in self._cache:
            return self._cache[original]

        seed = hash(original) % (2**32)
        rng = random.Random(seed)
        gen = RandomizedStrategy.GENERATORS.get(entity_type.upper())
        if gen:
            result = gen()
        else:
            result = ''.join(rng.choices(string.ascii_letters + string.digits, k=len(original)))
        self._cache[original] = result
        return result


class Anonymizer:
    STRATEGIES = {
        PolicyType.REDACT: RedactStrategy(),
        (PolicyType.ANONYMIZE, AnonymizeStrategy.RANDOMIZED): RandomizedStrategy(),
        (PolicyType.ANONYMIZE, AnonymizeStrategy.ALTERNATE): AlternateStrategy(),
    }

    def __init__(self):
        self._alternate_cache = AlternateStrategy()

    async def apply(
        self,
        text: str,
        entities: list,
        policies: list[PIIPolicy],
        context_hash: str,
        token_store,
        org_id: str,
    ) -> tuple[str, list]:
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
        mappings = []
        result = text

        for entity in sorted_entities:
            policy = self._find_policy(entity.entity, policies)
            if not policy or policy.policy_type == PolicyType.IGNORE:
                continue

            original = text[entity.start:entity.end]
            strategy = self.STRATEGIES.get(
                (policy.policy_type, policy.anonymize_strategy)
                if policy.policy_type == PolicyType.ANONYMIZE
                else policy.policy_type
            )

            if not strategy:
                continue

            tokenized = strategy.anonymize(original, entity.entity, policy)

            policy_applied_str = policy.policy_type.value if hasattr(policy.policy_type, 'value') else policy.policy_type
            mapping = TokenMapping(
                org_id=org_id,
                original_value=original,
                tokenized_value=tokenized,
                entity_type=entity.entity,
                policy_applied=policy_applied_str,
                context_hash=context_hash,
                confidence=entity.confidence,
                created_at=datetime.utcnow(),
            )
            await token_store.save(mapping)
            mappings.append(mapping)

            result = result[:entity.start] + tokenized + result[entity.end:]

        return result, mappings

    def _find_policy(self, entity_type: str, policies: list[PIIPolicy]) -> Optional[PIIPolicy]:
        for policy in policies:
            if policy.entity_type.upper() == entity_type.upper():
                return policy if policy.policy_type != PolicyType.IGNORE else None
        return None


anonymizer = Anonymizer()