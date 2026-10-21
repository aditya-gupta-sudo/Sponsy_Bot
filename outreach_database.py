
# outreach_database.py

import json

from database import get_connection


def set_sponsor_selection(event_id, company_id, user_id, status):
    """Select or reject a candidate belonging to this user's event."""

    if status not in {"SELECTED", "REJECTED"}:
        raise ValueError("Status must be SELECTED or REJECTED.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT ec.status
            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND ec.company_id = %s
            LIMIT 1
            """,
            (event_id, user_id, company_id),
        )

        row = cursor.fetchone()

        if row is None:
            return False

        current_status = row[0]

        # Do not undo a completed outreach state accidentally.
        if current_status in {"CONTACTED", "CLOSED"}:
            raise ValueError(
                "This sponsor already has an outreach status and "
                "cannot be selected or rejected using this operation."
            )

        cursor.execute(
            """
            UPDATE event_companies AS ec
            JOIN events AS e
                ON e.event_id = ec.event_id
            SET ec.status = %s
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND ec.company_id = %s
            """,
            (status, event_id, user_id, company_id),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_selected_company(event_id, company_id, user_id):
    """Get the event and sponsor details only for a selected sponsor."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                e.event_id,
                e.event_name,
                e.college,
                e.city AS event_city,
                e.state AS event_state,
                e.event_date,
                e.expected_participants,
                e.event_type,
                e.description,
                e.sponsorship_requirements,
                e.age_groups,
                e.audience_types,
                e.interests,
                e.geographic_reach,
                e.spending_profile,
                e.event_format,

                c.company_id,
                c.company_name,
                c.website AS company_website,
                c.industry AS company_industry,
                ec.status AS sponsor_status,
                ec.ai_score,
                ec.human_rank,

                (
                    SELECT crs.source_title
                    FROM company_research_sources AS crs
                    WHERE crs.event_id = e.event_id
                      AND crs.company_id = c.company_id
                    ORDER BY crs.source_id DESC
                    LIMIT 1
                ) AS source_title,

                (
                    SELECT crs.source_url
                    FROM company_research_sources AS crs
                    WHERE crs.event_id = e.event_id
                      AND crs.company_id = c.company_id
                    ORDER BY crs.source_id DESC
                    LIMIT 1
                ) AS source_url,

                (
                    SELECT crs.evidence_snippet
                    FROM company_research_sources AS crs
                    WHERE crs.event_id = e.event_id
                      AND crs.company_id = c.company_id
                    ORDER BY crs.source_id DESC
                    LIMIT 1
                ) AS evidence_snippet

            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            JOIN companies AS c
                ON c.company_id = ec.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND c.company_id = %s
              AND ec.status = 'SELECTED'
            LIMIT 1
            """,
            (event_id, user_id, company_id),
        )

        result = cursor.fetchone()

        if result is None:
            return None

        # Convert JSON columns into Python lists for the email generator.
        for field in ("age_groups", "audience_types", "interests"):
            value = result.get(field)

            if isinstance(value, str):
                try:
                    result[field] = json.loads(value)
                except json.JSONDecodeError:
                    result[field] = [
                        item.strip()
                        for item in value.split(",")
                        if item.strip()
                    ]
            elif value is None:
                result[field] = []

        requirements = result.get("sponsorship_requirements")

        if isinstance(requirements, str):
            try:
                result["sponsorship_requirements"] = json.loads(requirements)
            except json.JSONDecodeError:
                result["sponsorship_requirements"] = [
                    item.strip()
                    for item in requirements.split(",")
                    if item.strip()
                ]
        elif requirements is None:
            result["sponsorship_requirements"] = []

        return result

    finally:
        connection.close()


def save_sponsor_contacts(
    event_id, company_id, contacts, domain=None, website=None
):
    """Persist Hunter results and add a website if one is missing."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        if website:
            cursor.execute(
                """
                UPDATE companies
                SET website = COALESCE(NULLIF(website, ''), %s)
                WHERE company_id = %s
                """,
                (website, company_id),
            )

        saved_count = 0

        for item in contacts:
            email = (item.get("email_address") or "").strip().lower()

            if not email:
                continue

            cursor.execute(
                """
                INSERT INTO sponsor_contacts (
                    event_id,
                    company_id,
                    company_domain,
                    email_address,
                    full_name,
                    job_title,
                    department,
                    email_type,
                    confidence,
                    verification_status,
                    source_url,
                    found_via
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    contact_id = LAST_INSERT_ID(contact_id),
                    company_domain = COALESCE(
                        VALUES(company_domain), company_domain
                    ),
                    full_name = COALESCE(VALUES(full_name), full_name),
                    job_title = COALESCE(VALUES(job_title), job_title),
                    department = COALESCE(VALUES(department), department),
                    email_type = COALESCE(VALUES(email_type), email_type),
                    confidence = COALESCE(VALUES(confidence), confidence),
                    verification_status = COALESCE(
                        VALUES(verification_status), verification_status
                    ),
                    source_url = COALESCE(VALUES(source_url), source_url)
                """,
                (
                    event_id,
                    company_id,
                    domain,
                    email,
                    item.get("full_name"),
                    item.get("job_title"),
                    item.get("department"),
                    item.get("email_type"),
                    item.get("confidence"),
                    item.get("verification_status"),
                    item.get("source_url"),
                    item.get("found_via", "hunter"),
                ),
            )

            saved_count += 1

        connection.commit()
        return saved_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_sponsor_contacts(event_id, company_id, user_id):
    """List saved contacts for a selected sponsor and owned event."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT sc.*
            FROM sponsor_contacts AS sc
            JOIN events AS e
                ON e.event_id = sc.event_id
            JOIN event_companies AS ec
                ON ec.event_id = sc.event_id
               AND ec.company_id = sc.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND sc.company_id = %s
              AND ec.status = 'SELECTED'
            ORDER BY
                sc.confidence DESC,
                sc.email_address
            """,
            (event_id, user_id, company_id),
        )

        return cursor.fetchall()

    finally:
        connection.close()


def save_email_draft(
    event_id,
    company_id,
    contact_id,
    user_id,
    subject,
    body,
):
    """Save a draft only for a contact attached to a selected sponsor."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                sc.email_address,
                sc.full_name
            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            JOIN sponsor_contacts AS sc
                ON sc.event_id = ec.event_id
               AND sc.company_id = ec.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND ec.company_id = %s
              AND ec.status = 'SELECTED'
              AND sc.contact_id = %s
            LIMIT 1
            """,
            (event_id, user_id, company_id, contact_id),
        )

        contact = cursor.fetchone()

        if contact is None:
            return None

        cursor.execute(
            """
            INSERT INTO outreach_emails (
                event_id,
                company_id,
                contact_id,
                recipient_email,
                recipient_name,
                subject,
                body,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'DRAFT')
            """,
            (
                event_id,
                company_id,
                contact_id,
                contact["email_address"],
                contact["full_name"],
                subject,
                body,
            ),
        )

        email_id = cursor.lastrowid
        connection.commit()

        return email_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def claim_email_for_sending(email_id, event_id, user_id):
    """
    Atomically change DRAFT to SENDING.

    Only one request can claim a draft, preventing accidental duplicate
    sends caused by double-clicking the Send button.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT oe.*
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            JOIN event_companies AS ec
                ON ec.event_id = oe.event_id
               AND ec.company_id = oe.company_id
            WHERE oe.email_id = %s
              AND oe.event_id = %s
              AND e.user_id = %s
              AND ec.status = 'SELECTED'
            FOR UPDATE
            """,
            (email_id, event_id, user_id),
        )

        draft = cursor.fetchone()

        if draft is None or draft["status"] != "DRAFT":
            connection.rollback()
            return None

        cursor.execute(
            """
            UPDATE outreach_emails
            SET status = 'SENDING',
                approved_at = NOW(),
                error_message = NULL
            WHERE email_id = %s
              AND status = 'DRAFT'
            """,
            (email_id,),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return None

        connection.commit()
        return draft

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def finish_email_send(email_id, event_id, company_id, success, error=None):
    """Record the SMTP result and update sponsor status after success."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        if success:
            cursor.execute(
                """
                UPDATE outreach_emails
                SET status = 'SENT',
                    sent_at = NOW(),
                    error_message = NULL
                WHERE email_id = %s
                  AND event_id = %s
                  AND status = 'SENDING'
                """,
                (email_id, event_id),
            )

            if cursor.rowcount != 1:
                raise RuntimeError("Could not finalize the send record.")

            cursor.execute(
                """
                UPDATE event_companies
                SET status = 'CONTACTED'
                WHERE event_id = %s
                  AND company_id = %s
                  AND status = 'SELECTED'
                """,
                (event_id, company_id),
            )

        else:
            cursor.execute(
                """
                UPDATE outreach_emails
                SET status = 'FAILED',
                    error_message = %s
                WHERE email_id = %s
                  AND event_id = %s
                  AND status = 'SENDING'
                """,
                ((error or "SMTP send failed.")[:4000], email_id, event_id),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_outreach_history(event_id, user_id):
    """Return stored drafts and send records for an event."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                oe.email_id,
                oe.event_id,
                oe.company_id,
                c.company_name,
                oe.contact_id,
                oe.recipient_email,
                oe.recipient_name,
                oe.subject,
                oe.body,
                oe.status,
                oe.approved_at,
                oe.sent_at,
                oe.error_message,
                oe.created_at,
                oe.reply_status,
                oe.reply_received_at,
                oe.reply_from_email,
                oe.reply_subject,
                oe.reply_snippet,
                oe.reply_gmail_message_id,
                oe.reply_decision,
                oe.updated_at
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            JOIN companies AS c
                ON c.company_id = oe.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
            ORDER BY oe.created_at DESC
            """,
            (event_id, user_id),
        )

        return cursor.fetchall()

    finally:
        connection.close()



def update_email_draft(email_id, event_id, user_id, subject, body):
    """Edit an existing unsent draft, including when values are unchanged."""

    if not subject.strip() or not body.strip():
        raise ValueError("Subject and body must not be empty.")

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT oe.email_id
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            JOIN event_companies AS ec
                ON ec.event_id = oe.event_id
               AND ec.company_id = oe.company_id
            WHERE oe.email_id = %s
              AND oe.event_id = %s
              AND e.user_id = %s
              AND oe.status = 'DRAFT'
              AND ec.status = 'SELECTED'
            LIMIT 1
            FOR UPDATE
            """,
            (email_id, event_id, user_id),
        )

        if cursor.fetchone() is None:
            connection.rollback()
            return False

        cursor.execute(
            """
            UPDATE outreach_emails
            SET subject = %s,
                body = %s
            WHERE email_id = %s
              AND event_id = %s
              AND status = 'DRAFT'
            """,
            (subject, body, email_id, event_id),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_all_outreach_history(
    user_id,
    search=None,
    status=None,
    sort_by="newest",
):
    """Return outreach records from all of this user's events."""

    allowed_sorts = {
        "newest": "oe.created_at DESC, oe.email_id DESC",
        "oldest": "oe.created_at ASC, oe.email_id ASC",
        "company": "c.company_name ASC, oe.created_at DESC",
        "event": "e.event_name ASC, oe.created_at DESC",
        "recipient": "oe.recipient_email ASC, oe.created_at DESC",
        "status": "oe.status ASC, oe.created_at DESC",
    }

    order_clause = allowed_sorts.get(sort_by)
    if order_clause is None:
        raise ValueError("Unsupported outreach sort order.")

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                oe.email_id,
                oe.event_id,
                e.event_name,
                oe.company_id,
                c.company_name,
                c.industry,
                oe.contact_id,
                oe.recipient_email,
                oe.recipient_name,
                oe.subject,
                oe.body,
                oe.status,
                oe.approved_at,
                oe.sent_at,
                oe.error_message,
                oe.created_at,
                oe.reply_status,
                oe.reply_received_at,
                oe.reply_from_email,
                oe.reply_subject,
                oe.reply_snippet,
                oe.reply_gmail_message_id,
                oe.reply_decision,
                oe.updated_at
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            JOIN companies AS c
                ON c.company_id = oe.company_id
            WHERE e.user_id = %s
        """

        values = [user_id]

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query += """
                AND (
                    c.company_name LIKE %s
                    OR e.event_name LIKE %s
                    OR oe.recipient_email LIKE %s
                    OR COALESCE(oe.subject, '') LIKE %s
                )
            """
            values.extend([pattern, pattern, pattern, pattern])

        if status and status.strip():
            query += " AND oe.status = %s "
            values.append(status.strip().upper())

        query += f" ORDER BY {order_clause}"

        cursor.execute(query, tuple(values))
        return cursor.fetchall()

    finally:
        connection.close()


def delete_event_sponsor(event_id, company_id, user_id):
    """Remove a candidate from one owned event only when no outreach history exists.

    Global company data is retained. Existing draft/sent records are never deleted
    as a side effect; the user must retain history rather than orphaning it.
    """
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT ec.status FROM events e
               JOIN event_companies ec ON ec.event_id = e.event_id
               WHERE e.event_id = %s AND e.user_id = %s AND ec.company_id = %s
               LIMIT 1 FOR UPDATE""",
            (event_id, user_id, company_id),
        )
        link = cursor.fetchone()
        if not link:
            connection.rollback()
            return False

        cursor.execute(
            "SELECT COUNT(*) AS total FROM outreach_emails WHERE event_id = %s AND company_id = %s",
            (event_id, company_id),
        )
        history_count = int((cursor.fetchone() or {}).get("total") or 0)
        if history_count:
            connection.rollback()
            raise ValueError(
                "This sponsor has saved email or send history. It cannot be deleted without losing the audit trail."
            )

        # Child records are event-scoped; global company records are not touched.
        cursor.execute(
            "DELETE FROM sponsor_contacts WHERE event_id = %s AND company_id = %s",
            (event_id, company_id),
        )
        cursor.execute(
            "DELETE FROM company_research_sources WHERE event_id = %s AND company_id = %s",
            (event_id, company_id),
        )
        cursor.execute(
            """DELETE ec FROM event_companies ec
               JOIN events e ON e.event_id = ec.event_id
               WHERE ec.event_id = %s AND ec.company_id = %s AND e.user_id = %s""",
            (event_id, company_id, user_id),
        )
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_outreach_record(email_id, user_id):
    """Permanently delete an outreach record owned by this user."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT oe.status
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            WHERE oe.email_id = %s
              AND e.user_id = %s
            FOR UPDATE
            """,
            (email_id, user_id),
        )

        record = cursor.fetchone()

        if record is None:
            connection.rollback()
            return False

        if record["status"] == "SENDING":
            connection.rollback()
            raise ValueError(
                "This record is currently marked SENDING. "
                "Verify delivery status before deleting it."
            )

        cursor.execute(
            """
            DELETE FROM outreach_emails
            WHERE email_id = %s
            """,
            (email_id,),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()