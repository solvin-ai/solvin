# frontend/Dockerfile
FROM node:24-bullseye

WORKDIR /app
COPY ["package*.json", ".", "."]

ENV PATH /app/node_modules/.bin:$PATH

RUN rm -rf node_modules .next 
RUN npm ci

EXPOSE 3000

# For dev: still run the dev server
CMD ["npm", "run", "dev"]
