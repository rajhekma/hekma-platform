import copy
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from api.services.crypto import crypto_engine
from api.services.token_store import token_store
from api.models.token_mapping import TokenMapping

logger = logging.getLogger("pii-phi.fhir")

# Clinical keys that must NEVER be masked (preserve LOINC, SNOMED, RxNorm, dosages, vitals)
PRESERVED_CLINICAL_KEYS = {
    "code",
    "coding",
    "system",
    "display",
    "clinicalstatus",
    "verificationstatus",
    "category",
    "medicationcodeableconcept",
    "valuequantity",
    "unit",
    "dosageinstruction",
    "doseandrate",
    "route",
    "method",
    "referencerange",
    "interpretation",
    "component",
    "status",
    "intent",
    "priority",
}


class FHIRAnonymizer:
    """Recursively walks FHIR JSON structures to tokenize Safe Harbor 18 PHI/PII

    while explicitly preserving clinical terminology (LOINC, SNOMED, RxNorm).
    """

    def __init__(self, crypto=None):
        self._crypto = crypto or crypto_engine

    async def anonymize_fhir_resource(
        self,
        resource: Dict[str, Any],
        org_id: str = "default",
        patient_salt: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[TokenMapping]]:
        """Anonymizes a single FHIR resource or FHIR Bundle, returning sanitized resource and created token mappings."""
        res_copy = copy.deepcopy(resource)
        mappings: List[TokenMapping] = []

        res_type = res_copy.get("resourceType", "")

        # If it's a Bundle, recursively process each entry
        if res_type == "Bundle" and "entry" in res_copy:
            for entry in res_copy.get("entry", []):
                if isinstance(entry, dict) and "resource" in entry:
                    sub_res, sub_mappings = await self.anonymize_fhir_resource(
                        entry["resource"], org_id, patient_salt
                    )
                    entry["resource"] = sub_res
                    mappings.extend(sub_mappings)
            return res_copy, mappings

        # Process single resource
        await self._walk_and_anonymize(res_copy, org_id, mappings, path="")
        return res_copy, mappings

    async def _walk_and_anonymize(
        self,
        node: Any,
        org_id: str,
        mappings: List[TokenMapping],
        path: str,
    ) -> Any:
        if isinstance(node, dict):
            # Check for Patient resource specific fields
            if node.get("resourceType") == "Patient":
                await self._anonymize_patient_node(node, org_id, mappings)

            for key, val in list(node.items()):
                lower_key = key.lower()
                current_path = f"{path}.{key}" if path else key

                # Skip explicitly preserved clinical vocabulary branches
                if lower_key in PRESERVED_CLINICAL_KEYS:
                    continue

                # Anonymize direct identifiers
                if lower_key in ("reference",) and isinstance(val, str) and "Patient/" in val:
                    node[key] = await self._anonymize_patient_reference(val, org_id, mappings)
                    continue

                if lower_key in ("reference",) and isinstance(val, str) and "Practitioner/" in val:
                    node[key] = await self._anonymize_practitioner_reference(val, org_id, mappings)
                    continue

                # Provider display masking in performer / participant / recorder / asserter
                if lower_key in ("performer", "participant", "recorder", "asserter"):
                    await self._anonymize_provider_node(val, org_id, mappings)

                # Free-text clinical narrative / notes
                if lower_key in ("text", "note", "div", "description", "comment", "narrative"):
                    if isinstance(val, str):
                        node[key] = await self._anonymize_narrative_text(val, org_id, mappings)
                    elif isinstance(val, list):
                        node[key] = [
                            await self._anonymize_narrative_item(item, org_id, mappings)
                            for item in val
                        ]
                    elif isinstance(val, dict):
                        await self._walk_and_anonymize(val, org_id, mappings, current_path)
                    continue

                # Recursive walk for other fields
                node[key] = await self._walk_and_anonymize(val, org_id, mappings, current_path)
            return node

        elif isinstance(node, list):
            return [
                await self._walk_and_anonymize(item, org_id, mappings, path)
                for item in node
            ]

        return node

    async def _anonymize_patient_node(
        self, patient: Dict[str, Any], org_id: str, mappings: List[TokenMapping]
    ) -> None:
        # 1. Patient ID
        if "id" in patient and isinstance(patient["id"], str):
            orig_id = patient["id"]
            anon_id = self._crypto.generate_deterministic_token("PAT", orig_id, length=10)
            patient["id"] = anon_id
            await self._record_mapping(org_id, orig_id, anon_id, "PATIENT_ID", mappings)

        # 2. Names
        if "name" in patient and isinstance(patient["name"], list):
            for name_entry in patient["name"]:
                if isinstance(name_entry, dict):
                    if "text" in name_entry and isinstance(name_entry["text"], str):
                        orig_text = name_entry["text"]
                        anon_text = self._crypto.generate_deterministic_token("NAME", orig_text)
                        name_entry["text"] = anon_text
                        await self._record_mapping(org_id, orig_text, anon_text, "PERSON", mappings)

                    if "family" in name_entry and isinstance(name_entry["family"], str):
                        orig_fam = name_entry["family"]
                        anon_fam = self._crypto.generate_deterministic_token("FAM", orig_fam)
                        name_entry["family"] = anon_fam
                        await self._record_mapping(org_id, orig_fam, anon_fam, "PERSON", mappings)

                    if "given" in name_entry and isinstance(name_entry["given"], list):
                        new_given = []
                        for g in name_entry["given"]:
                            if isinstance(g, str):
                                anon_g = self._crypto.generate_deterministic_token("GIVEN", g)
                                new_given.append(anon_g)
                                await self._record_mapping(org_id, g, anon_g, "PERSON", mappings)
                            else:
                                new_given.append(g)
                        name_entry["given"] = new_given

        # 3. Telecom (Phone / Email)
        if "telecom" in patient and isinstance(patient["telecom"], list):
            for tc in patient["telecom"]:
                if isinstance(tc, dict) and "value" in tc and isinstance(tc["value"], str):
                    orig_val = tc["value"]
                    system = tc.get("system", "phone")
                    prefix = "EMAIL" if "email" in system.lower() else "PHONE"
                    anon_val = self._crypto.generate_deterministic_token(prefix, orig_val)
                    tc["value"] = anon_val
                    await self._record_mapping(org_id, orig_val, anon_val, prefix, mappings)

        # 4. Address (Street, City, Zip)
        if "address" in patient and isinstance(patient["address"], list):
            for addr in patient["address"]:
                if isinstance(addr, dict):
                    if "line" in addr and isinstance(addr["line"], list):
                        addr["line"] = ["[REDACTED STREET ADDRESS]"]
                    if "postalCode" in addr and isinstance(addr["postalCode"], str):
                        orig_zip = addr["postalCode"].strip()
                        # Safe Harbor: 3-digit zip if pop > 20,000, else 000
                        clean_zip = orig_zip.split("-")[0]
                        anon_zip = clean_zip[:3] + "XX" if len(clean_zip) >= 3 else "000XX"
                        addr["postalCode"] = anon_zip
                        await self._record_mapping(org_id, orig_zip, anon_zip, "ZIP_CODE", mappings)
                    if "city" in addr and isinstance(addr["city"], str):
                        orig_city = addr["city"]
                        anon_city = self._crypto.generate_deterministic_token("CITY", orig_city)
                        addr["city"] = anon_city
                        await self._record_mapping(org_id, orig_city, anon_city, "CITY", mappings)

        # 5. Identifier (MRN, SSN, DL)
        if "identifier" in patient and isinstance(patient["identifier"], list):
            for ident in patient["identifier"]:
                if isinstance(ident, dict) and "value" in ident and isinstance(ident["value"], str):
                    orig_ident = ident["value"]
                    anon_ident = self._crypto.generate_deterministic_token("ID", orig_ident)
                    ident["value"] = anon_ident
                    await self._record_mapping(org_id, orig_ident, anon_ident, "IDENTIFIER", mappings)

        # 6. Emergency Contacts & Next of Kin (patient.contact[])
        if "contact" in patient and isinstance(patient["contact"], list):
            for contact in patient["contact"]:
                if isinstance(contact, dict):
                    # Contact Name
                    c_name = contact.get("name")
                    if isinstance(c_name, dict):
                        if "text" in c_name and isinstance(c_name["text"], str):
                            orig_ctext = c_name["text"]
                            anon_ctext = self._crypto.generate_deterministic_token("NAME", orig_ctext)
                            c_name["text"] = anon_ctext
                            await self._record_mapping(org_id, orig_ctext, anon_ctext, "PERSON", mappings)
                        if "family" in c_name and isinstance(c_name["family"], str):
                            orig_cfam = c_name["family"]
                            anon_cfam = self._crypto.generate_deterministic_token("FAM", orig_cfam)
                            c_name["family"] = anon_cfam
                            await self._record_mapping(org_id, orig_cfam, anon_cfam, "PERSON", mappings)
                        if "given" in c_name and isinstance(c_name["given"], list):
                            new_cgiven = []
                            for cg in c_name["given"]:
                                if isinstance(cg, str):
                                    anon_cg = self._crypto.generate_deterministic_token("GIVEN", cg)
                                    new_cgiven.append(anon_cg)
                                    await self._record_mapping(org_id, cg, anon_cg, "PERSON", mappings)
                                else:
                                    new_cgiven.append(cg)
                            c_name["given"] = new_cgiven

                    # Contact Telecom
                    if "telecom" in contact and isinstance(contact["telecom"], list):
                        for c_tc in contact["telecom"]:
                            if isinstance(c_tc, dict) and "value" in c_tc and isinstance(c_tc["value"], str):
                                orig_cval = c_tc["value"]
                                c_system = c_tc.get("system", "phone")
                                c_prefix = "EMAIL" if "email" in c_system.lower() else "PHONE"
                                anon_cval = self._crypto.generate_deterministic_token(c_prefix, orig_cval)
                                c_tc["value"] = anon_cval
                                await self._record_mapping(org_id, orig_cval, anon_cval, c_prefix, mappings)

        # 7. Safe Harbor Birth Date Truncation (YYYY-01-01)
        if "birthDate" in patient and isinstance(patient["birthDate"], str):
            raw_bdate = patient["birthDate"].strip()
            if len(raw_bdate) >= 4 and raw_bdate[:4].isdigit():
                patient["birthDate"] = f"{raw_bdate[:4]}-01-01"

    async def _anonymize_patient_reference(
        self, ref_str: str, org_id: str, mappings: List[TokenMapping]
    ) -> str:
        if "Patient/" in ref_str:
            prefix, orig_id = ref_str.rsplit("Patient/", 1)
            orig_id = orig_id.split("?")[0].split("#")[0]
            anon_id = self._crypto.generate_deterministic_token("PAT", orig_id, length=10)
            await self._record_mapping(org_id, orig_id, anon_id, "PATIENT_ID", mappings)
            return f"{prefix}Patient/{anon_id}"
        return ref_str

    async def _anonymize_practitioner_reference(
        self, ref_str: str, org_id: str, mappings: List[TokenMapping]
    ) -> str:
        if "Practitioner/" in ref_str:
            prefix, orig_id = ref_str.rsplit("Practitioner/", 1)
            orig_id = orig_id.split("?")[0].split("#")[0]
            anon_id = self._crypto.generate_deterministic_token("DOC", orig_id, length=10)
            await self._record_mapping(org_id, orig_id, anon_id, "PRACTITIONER_ID", mappings)
            return f"{prefix}Practitioner/{anon_id}"
        return ref_str

    async def _anonymize_provider_node(
        self, node: Any, org_id: str, mappings: List[TokenMapping]
    ) -> None:
        if isinstance(node, list):
            for item in node:
                await self._anonymize_provider_node(item, org_id, mappings)
        elif isinstance(node, dict):
            if "display" in node and isinstance(node["display"], str) and node["display"].strip():
                orig_display = node["display"].strip()
                if not orig_display.startswith("[PERSON_"):
                    anon_token = self._crypto.generate_deterministic_token("PERSON", orig_display)
                    node["display"] = f"[{anon_token}]"
                    await self._record_mapping(org_id, orig_display, f"[{anon_token}]", "PERSON", mappings)
            if "actor" in node and isinstance(node["actor"], dict):
                await self._anonymize_provider_node(node["actor"], org_id, mappings)
            if "individual" in node and isinstance(node["individual"], dict):
                await self._anonymize_provider_node(node["individual"], org_id, mappings)

    async def _anonymize_narrative_text(
        self, text: str, org_id: str, mappings: List[TokenMapping]
    ) -> str:
        # Quick regex check for standard PII before ML scanning if text is short
        from api.main import detect_entities
        try:
            entities = await detect_entities(text)
            if not entities:
                return text
            
            result = text
            for ent in sorted(entities, key=lambda e: e["start"], reverse=True):
                orig_span = text[ent["start"] : ent["end"]]
                anon_token = self._crypto.generate_deterministic_token(ent["entity"], orig_span)
                await self._record_mapping(org_id, orig_span, anon_token, ent["entity"], mappings)
                result = result[: ent["start"]] + f"[{anon_token}]" + result[ent["end"] :]
            return result
        except Exception as e:
            logger.warning("Narrative text anonymization failed: %s", e)
            return text

    async def _anonymize_narrative_item(
        self, item: Any, org_id: str, mappings: List[TokenMapping]
    ) -> Any:
        if isinstance(item, str):
            return await self._anonymize_narrative_text(item, org_id, mappings)
        elif isinstance(item, dict):
            if "text" in item and isinstance(item["text"], str):
                item["text"] = await self._anonymize_narrative_text(item["text"], org_id, mappings)
        return item

    async def _record_mapping(
        self,
        org_id: str,
        original_value: str,
        tokenized_value: str,
        entity_type: str,
        mappings: List[TokenMapping],
    ) -> None:
        mapping = TokenMapping(
            org_id=org_id,
            original_value=original_value,
            tokenized_value=tokenized_value,
            entity_type=entity_type,
            policy_applied="anonymize",
            confidence=1.0,
        )
        try:
            await token_store.save(mapping)
            mappings.append(mapping)
        except Exception as e:
            logger.error("Failed to save token mapping: %s", e)


fhir_anonymizer = FHIRAnonymizer()
