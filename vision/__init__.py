"""
vision/ — Face detection and recognition for Table Tot.

Pipeline:  camera frame → YuNet (detect) → SFace (embed) → match → student_id

Every model here is pretrained and runs on-device. No face image is ever
persisted — only the 128-d embedding vectors, which cannot be turned back
into a photograph.
"""
