FROM node:20-slim

WORKDIR /app

# Copy package manifests and install dependencies
COPY package*.json ./
RUN npm install

# Copy source code and TypeScript config
COPY src/ ./src/
COPY tsconfig.json ./

# Build TypeScript to JavaScript
RUN npm run build

# Create session directory
RUN mkdir -p /app/session

EXPOSE 3001

CMD ["node", "dist/index.js"]
