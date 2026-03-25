import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List

import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------------------
# Firebase initialisation
# ---------------------------------------------------------------------------
_cred_path = os.path.join(os.path.dirname(__file__), "firebase-service-credentials.json")
cred = credentials.Certificate(_cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI()

# Allow requests from any origin (frontend served locally via file:// or a different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Serve the frontend
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "Frontend")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(_frontend_dir, "index.html"))


app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TapRecord(BaseModel):
    tapSequenceNumber: int
    startTimestamp: int
    endTimestamp: int
    interfaceSequence: int
    interface: str  # "feedbackshown" or "nofeedback"


class TapSession(BaseModel):
    id: str            # unique session identifier
    var: str           # device platform (e.g. "android" or "pc")
    taps: List[TapRecord]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@app.post("/save-taps")
async def save_taps(session: TapSession):
    """
    Receive tap-logging data from the frontend and persist it to Firestore.

    Firestore structure
    -------------------
    tap_logs (collection)
      └── {sessionId} (document)
            ├── sessionId
            ├── devicePlatform
            ├── createdAt          (server timestamp)
            └── taps (subcollection)
                  └── {auto-id}
                        ├── tapSequenceNumber
                        ├── startTimestamp
                        ├── endTimestamp
                        ├── duration           (computed: end - start)
                        ├── interfaceType
                        └── interfaceSequence
    """
    try:
        # --- Session document ---
        session_ref = db.collection("tap_logs").document(session.id)
        session_ref.set({
            "sessionId": session.id,
            "devicePlatform": session.var,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })

        # --- Individual tap documents (subcollection) ---
        taps_collection = session_ref.collection("taps")
        for tap in session.taps:
            taps_collection.add({
                "tapSequenceNumber": tap.tapSequenceNumber,
                "startTimestamp": tap.startTimestamp,
                "endTimestamp": tap.endTimestamp,
                "duration": tap.endTimestamp - tap.startTimestamp,
                "interfaceType": tap.interface,
                "interfaceSequence": tap.interfaceSequence,
            })

        print(f"✔ Saved session {session.id} ({len(session.taps)} taps) to Firestore")
        return {"message": "Data saved successfully"}

    except Exception as e:
        print(f"✖ Firestore error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
