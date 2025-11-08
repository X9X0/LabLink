# LabLink - Quick Resume Guide

## Project Location
```bash
cd ~/LabLink
```

## Current Status
- **Phase 1:** Complete ✓ (Server implementation)
- **Phase 2:** Pending (GUI client)

## What's Implemented
- FastAPI server with REST API
- WebSocket streaming
- Equipment drivers: Rigol MSO2072A, BK 9206B/9130B, BK 1902B
- Full documentation in docs/

## To Run the Server
```bash
cd server
source venv/bin/activate  # Or: python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Server will run at: http://localhost:8000
API docs: http://localhost:8000/docs

## To Test
```bash
python test_client.py
```

## Key Files
- `README.md` - Project overview
- `docs/GETTING_STARTED.md` - Setup instructions
- `docs/API_REFERENCE.md` - Complete API documentation
- `docs/CONVERSATION_LOG.md` - Session summaries
- `docs/DEVELOPMENT_CONVERSATION_VERBOSE.md` - Detailed development log

## Next Steps (Phase 2)
- [ ] GUI client with PyQt6
- [ ] Network discovery (Raspberry Pi MAC scanner)
- [ ] SSH deployment wizard
- [ ] Real-time data visualization
- [ ] Multi-server management

## GitHub
Repository: https://github.com/X9X0/LabLink

To push changes:
```bash
git add .
git commit -m "Your message"
git push
```

## Equipment Supported
- Rigol MSO2072A (oscilloscope)
- BK Precision 9206B (power supply)
- BK Precision 9130B (triple output power supply)
- BK Precision 1902B (electronic load)

## Starting a New Session with Claude
Say: "Continue working on LabLink at ~/LabLink"
Reference this file or the conversation logs for context.
