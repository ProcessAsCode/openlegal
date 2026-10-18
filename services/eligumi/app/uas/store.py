"""
Agreement storage.

`AgreementStore` is a thin interface so the UI never depends on *where*
agreements live. Today only `LocalAgreementStore` exists (SQLite rows +
versioned XML files under /data/agreements/{tenant}/{id}/v{n}.xml). A
future `ProcessGitStore` — each saved version becomes a commit in a
ProcessGit repo — implements the same interface and drops in without any
router change.

Invariant: "Save" NEVER overwrites. It appends v(n+1), writes the file,
and advances Agreement.current_version.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select, desc

from models import Agreement, AgreementRevision
from . import parse as uas_parse

AGREEMENTS_ROOT = Path(os.getenv("AGREEMENTS_ROOT", "/data/agreements"))


class AgreementStore(ABC):
    @abstractmethod
    def create(self, *, tenant_id: int, xml: bytes, user_id: Optional[int],
               source: str, needs_review: bool, validation) -> Agreement: ...

    @abstractmethod
    def save_version(self, *, agreement: Agreement, xml: bytes,
                     user_id: Optional[int], change_note: Optional[str],
                     validation) -> AgreementRevision: ...

    @abstractmethod
    def get(self, tenant_id: int, agreement_id: int) -> Optional[Agreement]: ...

    @abstractmethod
    def current_xml(self, tenant_id: int, agreement_id: int) -> Optional[bytes]: ...

    @abstractmethod
    def revision_xml(self, tenant_id: int, agreement_id: int, version: int) -> Optional[bytes]: ...

    @abstractmethod
    def list(self, tenant_id: int, status: Optional[str] = None) -> list[Agreement]: ...

    @abstractmethod
    def list_revisions(self, tenant_id: int, agreement_id: int) -> list[AgreementRevision]: ...


class LocalAgreementStore(AgreementStore):
    def __init__(self, session: Session):
        self.s = session

    # --- helpers ------------------------------------------------------------

    def _dir(self, tenant_id: int, agreement_id: int) -> Path:
        d = AGREEMENTS_ROOT / str(tenant_id) / str(agreement_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _next_uas_id(self, tenant_id: int) -> str:
        year = datetime.utcnow().year
        n = self.s.exec(
            select(Agreement).where(Agreement.tenant_id == tenant_id)
        ).all()
        return f"AG-{year}-{len(n) + 1:04d}"

    def _apply_summary(self, ag: Agreement, xml: bytes, validation) -> None:
        data = uas_parse.parse(xml)
        summ = uas_parse.summarize(data)
        ag.title = summ["title"]
        ag.agreement_type = summ["agreement_type"]
        ag.profile = summ["profile"]
        ag.language = summ["language"] or "lv"
        ag.status = summ["status"] or "draft"
        ag.buyer_name = summ["buyer_name"]
        ag.supplier_name = summ["supplier_name"]
        ag.clause_count = summ["clause_count"]
        ag.standardization_ratio = summ["standardization_ratio"]
        if validation is not None:
            ag.last_validation_ok = validation.ok
            ag.last_validation_errors = len(validation.errors)
            ag.last_validation_warnings = len(validation.warnings)
        ag.updated_at = datetime.utcnow()

    # --- interface ----------------------------------------------------------

    def create(self, *, tenant_id, xml, user_id, source, needs_review, validation):
        ag = Agreement(
            tenant_id=tenant_id,
            uas_id=self._next_uas_id(tenant_id),
            source=source,
            needs_review=needs_review,
            created_by_user_id=user_id,
            current_version=0,
        )
        self._apply_summary(ag, xml, validation)
        self.s.add(ag)
        self.s.commit()
        self.s.refresh(ag)
        self.save_version(agreement=ag, xml=xml, user_id=user_id,
                          change_note="initial", validation=validation)
        return ag

    def save_version(self, *, agreement, xml, user_id, change_note, validation):
        version = (agreement.current_version or 0) + 1
        path = self._dir(agreement.tenant_id, agreement.id) / f"v{version}.xml"
        path.write_bytes(xml)

        rev = AgreementRevision(
            tenant_id=agreement.tenant_id,
            agreement_id=agreement.id,
            version=version,
            xml=xml.decode("utf-8"),
            xml_path=str(path),
            validation_ok=(validation.ok if validation is not None else None),
            validation_report_json=(json.dumps(validation.to_json(), ensure_ascii=False)
                                    if validation is not None else None),
            change_note=change_note,
            created_by_user_id=user_id,
        )
        self.s.add(rev)
        agreement.current_version = version
        self._apply_summary(agreement, xml, validation)
        self.s.add(agreement)
        self.s.commit()
        self.s.refresh(rev)
        return rev

    def get(self, tenant_id, agreement_id):
        ag = self.s.get(Agreement, agreement_id)
        if ag is None or ag.tenant_id != tenant_id or ag.is_deleted:
            return None
        return ag

    def current_xml(self, tenant_id, agreement_id):
        ag = self.get(tenant_id, agreement_id)
        if ag is None:
            return None
        return self.revision_xml(tenant_id, agreement_id, ag.current_version)

    def revision_xml(self, tenant_id, agreement_id, version):
        rev = self.s.exec(
            select(AgreementRevision)
            .where(AgreementRevision.agreement_id == agreement_id,
                   AgreementRevision.tenant_id == tenant_id,
                   AgreementRevision.version == version)
        ).first()
        if rev is None:
            return None
        return rev.xml.encode("utf-8")

    def list(self, tenant_id, status=None):
        q = select(Agreement).where(Agreement.tenant_id == tenant_id,
                                     Agreement.is_deleted == False)  # noqa: E712
        if status and status != "all":
            q = q.where(Agreement.status == status)
        q = q.order_by(desc(Agreement.updated_at))
        return list(self.s.exec(q).all())

    def list_revisions(self, tenant_id, agreement_id):
        q = (select(AgreementRevision)
             .where(AgreementRevision.agreement_id == agreement_id,
                    AgreementRevision.tenant_id == tenant_id)
             .order_by(desc(AgreementRevision.version)))
        return list(self.s.exec(q).all())

    def soft_delete(self, tenant_id, agreement_id) -> bool:
        ag = self.get(tenant_id, agreement_id)
        if ag is None:
            return False
        ag.is_deleted = True
        ag.updated_at = datetime.utcnow()
        self.s.add(ag)
        self.s.commit()
        return True
