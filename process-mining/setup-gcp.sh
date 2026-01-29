#!/bin/bash
# Setup Google Cloud for Process Mining

set -e

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"ocx-demo"}
REGION="us-central1"
LOCATION="us"

echo "🚀 Setting up Google Cloud for OCX Process Mining"
echo "=================================================="

# Step 1: Enable APIs
echo ""
echo "📋 Step 1: Enabling Google Cloud APIs..."
gcloud services enable documentai.googleapis.com --project=$PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
gcloud services enable storage.googleapis.com --project=$PROJECT_ID
gcloud services enable run.googleapis.com --project=$PROJECT_ID

# Step 2: Create Document AI Processor
echo ""
echo "📄 Step 2: Creating Document AI processor..."
PROCESSOR_ID=$(gcloud documentai processors create \
  --display-name="OCX Document Parser" \
  --type=FORM_PARSER_PROCESSOR \
  --location=$LOCATION \
  --project=$PROJECT_ID \
  --format="value(name)" | awk -F'/' '{print $NF}')

echo "Document AI Processor ID: $PROCESSOR_ID"
echo "export DOCUMENT_AI_PROCESSOR_ID=$PROCESSOR_ID" >> .env

# Step 3: Create Cloud Storage Bucket
echo ""
echo "💾 Step 3: Creating Cloud Storage bucket..."
BUCKET_NAME="${PROJECT_ID}-documents"
gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME/ || echo "Bucket may already exist"
echo "export DOCUMENT_STORAGE_BUCKET=$BUCKET_NAME" >> .env

# Step 4: Create Service Account
echo ""
echo "🔐 Step 4: Creating service account..."
SA_NAME="ocx-process-mining"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME \
  --display-name="OCX Process Mining Service Account" \
  --project=$PROJECT_ID || echo "Service account may already exist"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/documentai.apiUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin"

# Step 5: Create Service Account Key
echo ""
echo "🔑 Step 5: Creating service account key..."
gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=$SA_EMAIL \
  --project=$PROJECT_ID

echo "export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/service-account-key.json" >> .env

# Step 6: Build and Deploy
echo ""
echo "🐳 Step 6: Building Docker image..."
docker build -t gcr.io/$PROJECT_ID/process-mining:latest .

echo ""
echo "📤 Step 7: Pushing to Container Registry..."
docker push gcr.io/$PROJECT_ID/process-mining:latest

echo ""
echo "☁️  Step 8: Deploying to Cloud Run..."
gcloud run deploy process-mining \
  --image gcr.io/$PROJECT_ID/process-mining:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --service-account $SA_EMAIL \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars "DOCUMENT_AI_PROCESSOR_ID=$PROCESSOR_ID" \
  --set-env-vars "DOCUMENT_STORAGE_BUCKET=$BUCKET_NAME" \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10 \
  --project=$PROJECT_ID

# Get service URL
SERVICE_URL=$(gcloud run services describe process-mining \
  --region $REGION \
  --project=$PROJECT_ID \
  --format='value(status.url)')

echo ""
echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo "Document AI Processor ID: $PROCESSOR_ID"
echo "Storage Bucket: gs://$BUCKET_NAME"
echo ""
echo "Environment variables saved to .env"
echo ""
echo "Test the service:"
echo "curl $SERVICE_URL/health"
echo ""
echo "Upload a document:"
echo "curl -X POST $SERVICE_URL/api/v1/process-mining/complete-workflow \\"
echo "  -F 'file=@demo-documents/purchase_order_sop.txt' \\"
echo "  -F 'company_id=demo-company'"
