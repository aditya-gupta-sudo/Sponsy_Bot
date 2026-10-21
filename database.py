# Part A
# os — reads environment variables, such as the database username and password.
# Path — works with filesystem paths reliably on Windows.
# mysql.connector — provides Python functions for connecting to MySQL.
# load_dotenv — loads variables from a .env file into the environment.
import json
import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

# Part B
# Always load .env from the main SponsyBot folder.
# __file__ refers to the current Python file, database.py.
# .resolve() produces its absolute path.
# .parent gives its containing directory.
# BASE_DIR / ".env" constructs the path to .env.
BASE_DIR = Path(__file__).resolve().parent 
load_dotenv(BASE_DIR / ".env")
# This is why the code can find .env even if you start the application 
# from a different working directory.


# Part C
# Important: the function only opens a connection. 
# It doesn't create tables, insert data, or start the FastAPI server.
def get_connection():
    """Create and return a connection to the MySQL database."""

    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "sponsybot"),
    )


# Part D
# This function saves an event submitted to the application.

def save_event(event, user_id):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        query = """
            INSERT INTO events (
                user_id,
                event_name,
                college,
                city,
                state,
                event_date,
                expected_participants,
                event_type,
                description,
                sponsorship_requirements,
                age_groups,
                audience_types,
                interests,
                geographic_reach,
                spending_profile,
                event_format
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        values = (
            user_id,
            event.event_name,
            event.college,
            event.city,
            event.state,
            event.event_date,
            event.expected_participants,
            event.event_type,
            event.description,
            ", ".join(event.sponsorship_requirements),
            json.dumps(event.age_groups),
            json.dumps(event.audience_types),
            json.dumps(event.interests),
            event.geographic_reach,
            event.spending_profile,
            event.event_format,
        )

        cursor.execute(query, values)
        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def get_events(user_id):
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                event_id,
                user_id,
                event_name,
                college,
                city,
                state,
                event_date,
                expected_participants,
                event_type,
                description,
                sponsorship_requirements
            FROM events
            WHERE user_id = %s
            ORDER BY event_id DESC
        """

        cursor.execute(query, (user_id,))
        return cursor.fetchall()

    finally:
        connection.close()


def get_event_by_id(event_id, user_id):
    """Retrieve one event, including its audience profile."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                event_id,
                user_id,
                event_name,
                college,
                city,
                state,
                event_date,
                expected_participants,
                event_type,
                description,
                sponsorship_requirements,
                age_groups,
                audience_types,
                interests,
                geographic_reach,
                spending_profile,
                event_format
            FROM events
            WHERE event_id = %s AND user_id = %s
            LIMIT 1
        """

        cursor.execute(query, (event_id, user_id))
        event = cursor.fetchone()

        if event is None:
            return None

        # Normalize JSON fields for the discovery engine.
        for field in ("age_groups", "audience_types", "interests"):
            value = event[field]

            if isinstance(value, str):
                event[field] = json.loads(value)
            elif value is None:
                event[field] = []

        # Normalize the sponsorship requirements.
        requirements = event["sponsorship_requirements"]

        if isinstance(requirements, str):
            event["sponsorship_requirements"] = [
                item.strip()
                for item in requirements.split(",")
                if item.strip()
            ]
        elif requirements is None:
            event["sponsorship_requirements"] = []

        return event

    finally:
        connection.close()

def save_company_candidates(event_id, candidates):
    """
    Save extracted sponsor candidates and their evidence.

    Args:
        event_id: Existing event ID in the events table.
        candidates: List of candidate dictionaries from
                    company_candidates_test.json.

    Returns:
        A summary of the number of candidates processed.
    """

    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Confirm that the event exists before saving candidates.
        cursor.execute(
            "SELECT event_id FROM events WHERE event_id = %s",
            (event_id,)
        )

        if cursor.fetchone() is None:
            raise ValueError(f"Event ID {event_id} does not exist")

        saved_count = 0
        skipped_count = 0

        for candidate in candidates:
            company_name = (candidate.get("company_name") or "").strip()
            source_url = (candidate.get("source_url") or "").strip()

            # Both fields are necessary for a useful candidate record.
            if not company_name or not source_url:
                skipped_count += 1
                continue

            website = candidate.get("website")
            industry = candidate.get("industry")

            # 1. Insert the company if it does not already exist.
            # The UNIQUE constraint on company_name prevents duplicates.
            cursor.execute(
                """
                INSERT INTO companies (company_name, website, industry)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    company_id = LAST_INSERT_ID(company_id),
                    website = COALESCE(VALUES(website), website),
                    industry = COALESCE(VALUES(industry), industry)
                """,
                (company_name, website, industry)
            )

            company_id = cursor.lastrowid

            # 2. Link the company to this event.
            # Keep existing status and human ranking if the relationship
            # already exists. Convert ORGANIZER to BOTH when AI also finds it.
            cursor.execute(
                """
                INSERT INTO event_companies (
                    event_id,
                    company_id,
                    discovery_source,
                    ai_score,
                    status
                )
                VALUES (%s, %s, 'AI', NULL, 'DISCOVERED')
                ON DUPLICATE KEY UPDATE
                    discovery_source = CASE
                        WHEN discovery_source = 'ORGANIZER' THEN 'BOTH'
                        ELSE discovery_source
                    END
                """,
                (event_id, company_id)
            )

            # 3. Store the evidence associated with this candidate.
            cursor.execute(
                """
                INSERT INTO company_research_sources (
                    event_id,
                    company_id,
                    source_url,
                    source_title,
                    evidence_snippet,
                    research_type
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source_title = COALESCE(
                        VALUES(source_title), source_title
                    ),
                    evidence_snippet = COALESCE(
                        VALUES(evidence_snippet), evidence_snippet
                    ),
                    research_type = COALESCE(
                        VALUES(research_type), research_type
                    )
                """,
                (
                    event_id,
                    company_id,
                    source_url,
                    candidate.get("source_title"),
                    candidate.get("evidence_snippet"),
                    candidate.get("evidence_type")
                )
            )

            saved_count += 1

        # All inserts and updates succeed together, or are rolled back.
        connection.commit()

        return {
            "event_id": event_id,
            "saved_count": saved_count,
            "skipped_count": skipped_count
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_event_candidates(event_id, user_id):
    """Retrieve saved sponsor candidates and their research evidence."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                c.company_id,
                c.company_name,
                c.website,
                c.industry,
                ec.discovery_source,
                ec.ai_score,
                ec.human_rank,
                ec.status,
                crs.source_url,
                crs.source_title,
                crs.evidence_snippet,
                crs.research_type
            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            JOIN companies AS c
                ON c.company_id = ec.company_id
            LEFT JOIN company_research_sources AS crs
                ON crs.event_id = ec.event_id
                AND crs.company_id = ec.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
            ORDER BY c.company_name, crs.source_id
        """

        cursor.execute(query, (event_id, user_id))
        return cursor.fetchall()

    finally:
        connection.close()


def update_event(event_id, user_id, event):
    """Update an event only if it belongs to the specified user."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Confirm ownership before updating.
        cursor.execute(
            """
            SELECT event_id
            FROM events
            WHERE event_id = %s AND user_id = %s
            LIMIT 1
            """,
            (event_id, user_id),
        )

        if cursor.fetchone() is None:
            return False

        query = """
            UPDATE events
            SET
                event_name = %s,
                college = %s,
                city = %s,
                state = %s,
                event_date = %s,
                expected_participants = %s,
                event_type = %s,
                description = %s,
                sponsorship_requirements = %s,
                age_groups = %s,
                audience_types = %s,
                interests = %s,
                geographic_reach = %s,
                spending_profile = %s,
                event_format = %s
            WHERE event_id = %s AND user_id = %s
        """

        values = (
            event.event_name,
            event.college,
            event.city,
            event.state,
            event.event_date,
            event.expected_participants,
            event.event_type,
            event.description,
            ", ".join(event.sponsorship_requirements),
            json.dumps(event.age_groups),
            json.dumps(event.audience_types),
            json.dumps(event.interests),
            event.geographic_reach,
            event.spending_profile,
            event.event_format,
            event_id,
            user_id,
        )

        cursor.execute(query, values)
        connection.commit()

        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_sponsor_history(event_id, company_id, user_id):
    """Get workspace event appearances and sponsorship-related evidence."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        # Confirm that this company belongs to the requested event
        # and that the event belongs to this user.
        cursor.execute(
            """
            SELECT c.company_name
            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            JOIN companies AS c
                ON c.company_id = ec.company_id
            WHERE e.event_id = %s
              AND e.user_id = %s
              AND c.company_id = %s
            LIMIT 1
            """,
            (event_id, user_id, company_id),
        )

        company = cursor.fetchone()

        if company is None:
            return None

        # Other events in this user's workspace where this company appeared.
        cursor.execute(
            """
            SELECT
                e.event_id,
                e.event_name,
                e.event_date,
                ec.discovery_source,
                ec.status
            FROM events AS e
            JOIN event_companies AS ec
                ON ec.event_id = e.event_id
            WHERE ec.company_id = %s
              AND e.user_id = %s
              AND e.event_id <> %s
            ORDER BY e.event_date DESC, e.event_id DESC
            """,
            (company_id, user_id, event_id),
        )

        previous_events = cursor.fetchall()

        # Research records explicitly classified as sponsorship-related.
        cursor.execute(
            """
            SELECT
                crs.event_id AS research_event_id,
                e.event_name AS research_event_name,
                crs.source_title,
                crs.source_url,
                crs.evidence_snippet,
                crs.research_type
            FROM company_research_sources AS crs
            JOIN events AS e
                ON e.event_id = crs.event_id
            WHERE crs.company_id = %s
              AND e.user_id = %s
              AND LOCATE(
                    'sponsor',
                    LOWER(COALESCE(crs.research_type, ''))
                ) > 0
            ORDER BY crs.source_id DESC
            """,
            (company_id, user_id),
        )

        sponsorship_evidence = cursor.fetchall()

        return {
            "company_name": company["company_name"],
            "previous_events": previous_events,
            "sponsorship_evidence": sponsorship_evidence,
        }

    finally:
        connection.close()


def get_sponsor_directory(
    user_id,
    search=None,
    industry=None,
    sort_by="name",
):
    """List distinct sponsors across this user's events."""

    allowed_sorts = {
        "name": "c.company_name ASC",
        "name_desc": "c.company_name DESC",
        "industry": "c.industry ASC, c.company_name ASC",
        "events": "event_count DESC, c.company_name ASC",
        "recent": "latest_event_date DESC, c.company_name ASC",
    }

    order_clause = allowed_sorts.get(sort_by)
    if order_clause is None:
        raise ValueError("Unsupported sponsor sort order.")

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                c.company_id,
                c.company_name,
                c.website,
                c.industry,
                COUNT(DISTINCT e.event_id) AS event_count,
                MAX(e.event_date) AS latest_event_date,
                GROUP_CONCAT(
                    DISTINCT ec.status
                    ORDER BY ec.status
                    SEPARATOR ', '
                ) AS statuses,
                COUNT(
                    DISTINCT CASE
                        WHEN LOCATE(
                            'sponsor',
                            LOWER(COALESCE(crs.research_type, ''))
                        ) > 0
                        THEN crs.source_id
                    END
                ) AS sponsorship_evidence_count
            FROM companies AS c
            JOIN event_companies AS ec
                ON ec.company_id = c.company_id
            JOIN events AS e
                ON e.event_id = ec.event_id
            LEFT JOIN company_research_sources AS crs
                ON crs.event_id = ec.event_id
               AND crs.company_id = ec.company_id
            WHERE e.user_id = %s
        """

        values = [user_id]

        if search and search.strip():
            query += """
                AND (
                    c.company_name LIKE %s
                    OR COALESCE(c.industry, '') LIKE %s
                    OR COALESCE(c.website, '') LIKE %s
                )
            """
            pattern = f"%{search.strip()}%"
            values.extend([pattern, pattern, pattern])

        if industry and industry.strip():
            query += " AND COALESCE(c.industry, '') = %s "
            values.append(industry.strip())

        query += f"""
            GROUP BY
                c.company_id,
                c.company_name,
                c.website,
                c.industry
            ORDER BY {order_clause}
        """

        cursor.execute(query, tuple(values))
        return cursor.fetchall()

    finally:
        connection.close()


def get_sponsor_global_history(company_id, user_id):
    """Return a company's event appearances and research in this workspace."""

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                c.company_id,
                c.company_name,
                c.website,
                c.industry
            FROM companies AS c
            WHERE c.company_id = %s
              AND EXISTS (
                  SELECT 1
                  FROM event_companies AS ec
                  JOIN events AS e
                    ON e.event_id = ec.event_id
                  WHERE ec.company_id = c.company_id
                    AND e.user_id = %s
              )
            LIMIT 1
            """,
            (company_id, user_id),
        )

        company = cursor.fetchone()

        if company is None:
            return None

        cursor.execute(
            """
            SELECT
                e.event_id,
                e.event_name,
                e.event_date,
                e.event_type,
                ec.discovery_source,
                ec.status
            FROM event_companies AS ec
            JOIN events AS e
                ON e.event_id = ec.event_id
            WHERE ec.company_id = %s
              AND e.user_id = %s
            ORDER BY e.event_date DESC, e.event_id DESC
            """,
            (company_id, user_id),
        )

        event_history = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                crs.event_id AS research_event_id,
                e.event_name AS research_event_name,
                crs.source_title,
                crs.source_url,
                crs.evidence_snippet,
                crs.research_type
            FROM company_research_sources AS crs
            JOIN events AS e
                ON e.event_id = crs.event_id
            WHERE crs.company_id = %s
              AND e.user_id = %s
              AND LOCATE(
                    'sponsor',
                    LOWER(COALESCE(crs.research_type, ''))
                ) > 0
            ORDER BY crs.source_id DESC
            """,
            (company_id, user_id),
        )

        evidence = cursor.fetchall()

        return {
            "company": company,
            "event_history": event_history,
            "sponsorship_evidence": evidence,
        }

    finally:
        connection.close()


def get_event_progress(user_id):
    """Calculate workflow milestones for each of the user's events."""
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT
                    e.event_id,
                    e.event_name,
                    CASE WHEN TRIM(COALESCE(e.event_name, '')) <> ''
                               AND TRIM(COALESCE(e.college, '')) <> ''
                               AND TRIM(COALESCE(e.city, '')) <> ''
                               AND TRIM(COALESCE(e.state, '')) <> ''
                               AND e.event_date IS NOT NULL
                               AND COALESCE(e.expected_participants, 0) > 0
                               AND TRIM(COALESCE(e.event_type, '')) <> ''
                               AND TRIM(COALESCE(e.description, '')) <> ''
                         THEN 1 ELSE 0 END AS details_complete,
                    (SELECT COUNT(*) FROM event_companies ec
                     WHERE ec.event_id = e.event_id) AS sponsor_count,
                    (SELECT COUNT(*) FROM event_companies ec
                     WHERE ec.event_id = e.event_id AND ec.status IN ('SELECTED', 'CONTACTED', 'CLOSED')) AS selected_sponsor_count,
                    (SELECT COUNT(*) FROM sponsor_contacts sc
                     WHERE sc.event_id = e.event_id) AS contact_count,
                    (SELECT COUNT(*) FROM outreach_emails oe
                     WHERE oe.event_id = e.event_id AND oe.status IN ('DRAFT', 'SENDING', 'SENT', 'FAILED')) AS email_count,
                    (SELECT COUNT(*) FROM outreach_emails oe
                     WHERE oe.event_id = e.event_id AND oe.status = 'SENT') AS sent_email_count
                FROM events e
                WHERE e.user_id = %s
                ORDER BY e.event_id DESC""",
            (user_id,),
        )
        rows = cursor.fetchall()
        for row in rows:
            for key in ("event_id", "details_complete", "sponsor_count", "selected_sponsor_count", "contact_count", "email_count", "sent_email_count"):
                row[key] = int(row.get(key) or 0)
        return rows
    finally:
        connection.close()
