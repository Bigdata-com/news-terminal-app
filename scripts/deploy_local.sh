#!/bin/bash

# News Terminal Local Docker Deployment Script

set -e

echo "🐳 News Terminal Local Docker Deployment"
echo "========================================="

# Container and image names
CONTAINER_NAME="news-terminal"
IMAGE_NAME="news-terminal:latest"

# Load environment variables from .env file
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env..."
    export $(grep -v '^#' .env | xargs)
    echo "✅ Environment variables loaded"
else
    echo "⚠️  No .env file found"
    echo "   Creating a sample .env file..."
    echo "BIGDATA_API_KEY=your_api_key_here" > .env
    echo "   Please edit .env and add your actual API key, then run this script again"
    exit 1
fi

# Check if API key is set
if [ -z "$BIGDATA_API_KEY" ] || [ "$BIGDATA_API_KEY" = "your_api_key_here" ]; then
    echo "❌ BIGDATA_API_KEY not found or not configured in .env file"
    echo "   Please add your actual API key to .env file:"
    echo "   BIGDATA_API_KEY=bd_v1_your_key_here"
    exit 1
else
    echo "✅ BIGDATA_API_KEY found"
fi

# Check for Vertex AI service account file (optional)
SERVICE_ACCOUNT_FILE="gemini-product-sandbox-8ece44ee190e.json"
VOLUME_MOUNT=""
VERTEX_AI_ENV=""
if [ -f "$SERVICE_ACCOUNT_FILE" ]; then
    echo "✅ Vertex AI service account file found"
    echo "   Gemini will use Vertex AI authentication"
    VOLUME_MOUNT="-v $(pwd)/$SERVICE_ACCOUNT_FILE:/app/$SERVICE_ACCOUNT_FILE:ro"
    # Override the path for Docker container (will override .env value)
    VERTEX_AI_ENV="-e GOOGLE_APPLICATION_CREDENTIALS=/app/$SERVICE_ACCOUNT_FILE"
else
    echo "ℹ️  No Vertex AI service account file found (optional)"
    echo "   Gemini will use API key authentication if GEMINI_API_KEY is set"
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

echo "✅ Docker is running"

# Stop and remove existing container if it exists
echo "🛑 Stopping any existing containers..."
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "   Found existing container, removing..."
    docker stop "$CONTAINER_NAME" > /dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true
    echo "✅ Old container removed"
    # Give Docker a moment to release the port
    sleep 1
else
    echo "   No existing container found"
fi

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t "$IMAGE_NAME" .
echo "✅ Docker image built successfully"

# Run the container
echo "🚀 Starting container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p 8000:8000 \
    --env-file .env \
    $VERTEX_AI_ENV \
    $VOLUME_MOUNT \
    --restart unless-stopped \
    "$IMAGE_NAME"

echo "✅ Container started successfully"

# Wait a moment for the container to start
echo "⏳ Waiting for application to start..."
sleep 3

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "✅ Container is running"
else
    echo "❌ Container failed to start. Checking logs..."
    docker logs "$CONTAINER_NAME"
    exit 1
fi

# Test the health endpoint
echo "🏥 Testing health endpoint..."
for i in {1..10}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✅ Application is healthy and responding"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠️  Application is not responding yet, but container is running"
        echo "   Check logs with: docker logs $CONTAINER_NAME"
    else
        sleep 2
    fi
done

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📱 Your News Terminal is available at:"
echo "   http://localhost:8000"
echo ""
echo "🔧 Useful commands:"
echo "   docker logs $CONTAINER_NAME              # View logs"
echo "   docker logs -f $CONTAINER_NAME           # Follow logs"
echo "   docker stop $CONTAINER_NAME              # Stop container"
echo "   docker restart $CONTAINER_NAME           # Restart container"
echo "   docker exec -it $CONTAINER_NAME bash     # Shell into container"
echo "   docker stats $CONTAINER_NAME             # View resource usage"
echo ""
echo "💡 To rebuild and redeploy:"
echo "   ./scripts/deploy_local.sh"
echo ""
echo "✨ Local deployment successful! Your news terminal is live!"

