FROM nikolaik/python-nodejs:python3.9-nodejs18-bullseye

# Install the PM2 process manager for Node.js
RUN npm install pm2 -g

RUN pm2 install pm2-logrotate && pm2 set pm2-logrotate:compress true && pm2 set pm2-logrotate:retain 7

# Copy the application's dependencies files
COPY poetry.lock pyproject.toml ./

# Install the Python dependencies
RUN poetry install --no-dev

# Copy the rest of the application's files
COPY . .

# Expose the port that the application will listen on
EXPOSE 9060

ENTRYPOINT sh init_processes.sh

# Start the application using PM2
# CMD pm2 start pm2.config.js && pm2 logs --lines 100
