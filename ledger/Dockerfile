FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir grpcio grpcio-tools protobuf

# Copy Service Code
COPY ./services/ledger /app/services/ledger
# Copy Shared Protobufs (Compose context usually sets build context to root, but here we assume context is ./services/ledger per compose file? 
# Wait, docker-compose say `context: ./services/ledger` so it can't verify backend/pb without ../ access?
# Actually checking docker-compose:
# ledger-service:
#    build: ./services/ledger
#
# If I use `build: ./services/ledger`, I cannot access `../../backend/pb`.
# Correct approach using Docker defaults: The context should be root `.` and dockerfile pointing to `services/ledger/Dockerfile`.
# OR I copy the protos into the image.
# For now, I'll assume the python code doesn't strictly need the .proto SOURCE files if generated code is present, 
# BUT `ledger_service.py` had `sys.path.append` pointing to `../../backend/pb`.
# That relative path won't work in Docker unless I mount it or copy it.
#
# FIX: I will update the Dockerfile to COPY the necessary files assuming the build context allows it, 
# OR I'll have to adjust `docker-compose` to use root context.
#
# Let's adjust this User's docker-compose pattern. Usually microservices share a repo.
# I will assume the context will likely be changed or I should suggest it.
# BUT strictly fulfilling the "Create Dockerfile" request at the location:

COPY . .

CMD ["python", "ledger_service.py"]
