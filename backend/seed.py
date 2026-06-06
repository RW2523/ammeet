#!/usr/bin/env python3
"""
Seed script: Creates a demo workspace, people, meeting, context, questions, and runs proxy simulation.
Run: python seed.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.core.security import hash_password
from app.models.user import User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.meeting import (
    Meeting,
    MeetingMode,
    MeetingStatus,
    CaptureLevel,
    Person,
    ContextSource,
    Question,
    QuestionCategory,
    QuestionPriority,
)
from app.models.knowledge import RetentionPolicy

_settings = get_settings()

DEMO_TRANSCRIPT = """
Previous Meeting — Client Dashboard Review (May 30, 2026)

John: The API authentication flow is partially complete. We're blocked on token refresh logic. 
Expected to finish by end of this week.

Sarah: The client has reviewed the dashboard design. They want two changes — the color scheme 
and the font size in the header. Once those are done, they should be ready to approve.

David (Client): Can you confirm the delivery date? We need to know if we're still on track for June 15.

Sarah: We'll need to confirm that internally. John, does the API timeline affect the delivery date?

John: If we resolve the auth issue this week, frontend can start integration Monday. 
We should be fine for June 15.

David: Great. One more thing — the deployment pipeline has been causing issues. 
Is that going to be a problem?

John: I'll personally take ownership of stabilizing the pipeline. Target is end of this week.

Action Items:
- John: Fix API authentication (by June 7)
- John: Stabilize deployment pipeline (by June 7)
- Sarah: Make dashboard design changes (by June 8)
- Sarah: Follow up with client on approval (by June 9)
- Team: Confirm June 15 delivery date
"""

async def seed():
    engine = create_async_engine(_settings.database_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        # Create demo user (owner/Richard)
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.email == "richard@ammeet.io"))
        user = existing.scalar_one_or_none()
        if not user:
            user = User(
                email="richard@ammeet.io",
                hashed_password=hash_password("ammeet2026"),
                full_name="Richard Watson",
                is_superuser=True,
            )
            db.add(user)
            await db.flush()
            print(f"Created user: richard@ammeet.io / ammeet2026")
        else:
            print(f"User already exists: {user.email}")

        # Create workspace
        existing_ws = await db.execute(select(Workspace).where(Workspace.slug == "client-dashboard-project"))
        ws = existing_ws.scalar_one_or_none()
        if not ws:
            ws = Workspace(
                name="Client Dashboard Project",
                description="Q2 2026 client dashboard delivery — API + frontend + client approval",
                slug="client-dashboard-project",
            )
            db.add(ws)
            await db.flush()
            db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER))
            db.add(RetentionPolicy(workspace_id=ws.id))
            print(f"Created workspace: {ws.name} (id={ws.id})")
        else:
            print(f"Workspace already exists: {ws.name}")

        # Add people
        people_data = [
            {
                "name": "John Smith",
                "role": "Backend Developer",
                "responsibility": "API development, deployment pipeline",
                "current_work": "API authentication fix, pipeline stabilization",
                "decision_authority": "Technical decisions within scope",
                "follow_up": "Is API auth resolved? Is pipeline stable?",
                "email": "john@company.com",
                "is_external": False,
            },
            {
                "name": "Sarah Chen",
                "role": "Product Manager",
                "responsibility": "Dashboard scope, client communication",
                "current_work": "Dashboard design changes, delivery confirmation",
                "decision_authority": "Product scope decisions",
                "follow_up": "Did client approve dashboard? Confirmed June 15 date?",
                "email": "sarah@company.com",
                "is_external": False,
            },
            {
                "name": "David Lee",
                "role": "Client Lead",
                "responsibility": "Client approval, requirements sign-off",
                "current_work": "Reviewing dashboard design changes",
                "decision_authority": "Client approval authority — final say",
                "follow_up": "Has client approved dashboard? Is June 15 confirmed?",
                "email": "david@client.com",
                "is_external": True,
            },
            {
                "name": "Mike Torres",
                "role": "Frontend Developer",
                "responsibility": "Frontend integration",
                "current_work": "Waiting for API to start integration",
                "decision_authority": "Frontend technical decisions",
                "follow_up": "Ready to start once API is done?",
                "email": "mike@company.com",
                "is_external": False,
            },
        ]
        
        existing_people = await db.execute(select(Person).where(Person.workspace_id == ws.id))
        if not existing_people.scalars().first():
            for p in people_data:
                db.add(Person(workspace_id=ws.id, **p))
            await db.flush()
            print(f"Added {len(people_data)} people")

        # Create meeting
        existing_meeting = await db.execute(
            select(Meeting).where(Meeting.workspace_id == ws.id, Meeting.title == "Client Dashboard Follow-up (June 7)")
        )
        meeting = existing_meeting.scalar_one_or_none()
        if not meeting:
            meeting = Meeting(
                workspace_id=ws.id,
                title="Client Dashboard Follow-up (June 7)",
                purpose="Confirm API auth status, dashboard design approval, and June 15 delivery date",
                mode=MeetingMode.PROXY,
                status=MeetingStatus.READY,
                capture_level=CaptureLevel.TRANSCRIPT_AND_SUMMARY,
                proxy_consent_given=True,
            )
            db.add(meeting)
            await db.flush()
            print(f"Created meeting: {meeting.title} (id={meeting.id})")
        else:
            print(f"Meeting already exists: {meeting.title}")

        # Add previous transcript as context source
        existing_sources = await db.execute(
            select(ContextSource).where(ContextSource.meeting_id == meeting.id)
        )
        if not existing_sources.scalars().first():
            source = ContextSource(
                meeting_id=meeting.id,
                workspace_id=ws.id,
                source_type="upload",
                filename="previous_meeting_may30.txt",
                raw_text=DEMO_TRANSCRIPT,
                extraction_status="done",
                extracted_json=json.dumps({
                    "people": [{"name": "John", "role": "Backend Dev"}, {"name": "Sarah", "role": "PM"}, {"name": "David", "role": "Client"}],
                    "topics": ["API authentication", "Dashboard design", "Delivery date", "Deployment pipeline"],
                    "decisions": [
                        {"text": "John will own pipeline fix by June 7", "made_by": "John", "requires_approval": False},
                        {"text": "Dashboard design changes needed before client approval", "made_by": "Sarah", "requires_approval": False},
                    ],
                    "action_items": [
                        {"title": "Fix API authentication", "owner": "John", "deadline": "June 7"},
                        {"title": "Stabilize deployment pipeline", "owner": "John", "deadline": "June 7"},
                        {"title": "Make dashboard design changes", "owner": "Sarah", "deadline": "June 8"},
                        {"title": "Follow up with client on approval", "owner": "Sarah", "deadline": "June 9"},
                    ],
                    "risks": [
                        {"text": "API auth delay could push June 15 delivery", "severity": "high"},
                        {"text": "Deployment pipeline instability is a release risk", "severity": "medium"},
                    ],
                    "pending_questions": [
                        "Is API auth resolved?",
                        "Has client approved dashboard design?",
                        "Is June 15 delivery date confirmed?",
                        "Is pipeline stable?",
                    ],
                    "blockers": ["Token refresh logic", "Client dashboard approval pending"],
                    "summary": "API authentication is in progress with a blocker on token refresh. Dashboard design changes are needed before client approval. John owns pipeline stabilization. June 15 delivery target is at risk pending API completion.",
                }),
            )
            db.add(source)
            await db.flush()
            print("Added previous transcript context")

        # Generate smart questions
        existing_questions = await db.execute(
            select(Question).where(Question.meeting_id == meeting.id)
        )
        if not existing_questions.scalars().first():
            questions = [
                {
                    "text": "John, can you confirm whether the API authentication issue is now fully resolved and ready for frontend integration?",
                    "category": QuestionCategory.STATUS,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.95,
                    "source_context": "PROJ-101 was in progress, blocked on token refresh",
                    "sort_order": 0,
                },
                {
                    "text": "Sarah, has the client confirmed approval of the dashboard design changes?",
                    "category": QuestionCategory.CLIENT,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.92,
                    "source_context": "Client approval was pending after round 2",
                    "sort_order": 1,
                },
                {
                    "text": "Can the team confirm we are still on track for the June 15 delivery date?",
                    "category": QuestionCategory.DEADLINE,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.90,
                    "source_context": "Client asked for June 15 confirmation in last meeting",
                    "sort_order": 2,
                },
                {
                    "text": "John, has the deployment pipeline been stabilized? Any remaining risks?",
                    "category": QuestionCategory.RISK,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.88,
                    "source_context": "Pipeline instability was flagged as risk",
                    "sort_order": 3,
                },
                {
                    "text": "Mike, are you ready to start frontend integration once the API is confirmed ready?",
                    "category": QuestionCategory.OWNERSHIP,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.85,
                    "source_context": "Frontend was waiting on API",
                    "sort_order": 4,
                },
                {
                    "text": "Are there any new blockers or risks that have appeared since the last meeting?",
                    "category": QuestionCategory.BLOCKER,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.80,
                    "source_context": "General blocker check",
                    "sort_order": 5,
                },
                {
                    "text": "Does the client need a formal written approval for the design changes?",
                    "category": QuestionCategory.DECISION,
                    "priority": QuestionPriority.IF_TIME,
                    "proxy_allowed": True,
                    "human_only": False,
                    "confidence": 0.75,
                    "source_context": "Approval format not specified",
                    "sort_order": 6,
                },
                {
                    "text": "Can we get final budget approval for the additional design work?",
                    "category": QuestionCategory.DECISION,
                    "priority": QuestionPriority.MUST_ASK,
                    "proxy_allowed": False,
                    "human_only": True,
                    "confidence": 0.70,
                    "source_context": "Budget approval requires human decision",
                    "sort_order": 7,
                    "escalation_rule": "budget_approval",
                },
            ]
            
            for q_data in questions:
                question = Question(
                    meeting_id=meeting.id,
                    workspace_id=ws.id,
                    **q_data,
                )
                db.add(question)
            await db.flush()
            print(f"Added {len(questions)} smart questions ({sum(1 for q in questions if q['proxy_allowed'])} proxy-allowed, {sum(1 for q in questions if q['human_only'])} human-only)")

        await db.commit()
        
        print("\n" + "="*60)
        print("DEMO SEED COMPLETE")
        print("="*60)
        print(f"Login: richard@ammeet.io / ammeet2026")
        print(f"Workspace ID: {ws.id}")
        print(f"Meeting ID: {meeting.id}")
        print(f"\nTo run the proxy demo:")
        print(f"  POST /api/workspaces/{ws.id}/meetings/{meeting.id}/proxy/start?simulate=true")
        print(f"  Authorization: Bearer <your_token>")
        print("\nTo query the knowledge base:")
        print(f"  POST /api/workspaces/{ws.id}/knowledge/query")
        print(f"  {{\"query\": \"What was discussed about the API last meeting?\"}}")
        print("="*60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
