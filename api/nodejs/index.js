#!/usr/bin/env node
/**
 * DiashowDL Node.js API Demo
 * 
 * Controls a Diashow server via its REST API.
 */

const fs = require('fs');
const path = require('path');
const axios = require('axios');
const https = require('https');
const readline = require('readline');

const API_PORT = 9134;
const httpsAgent = new https.Agent({ rejectUnauthorized: false });

/**
 * Generic API caller
 */
async function api(host, key, method, path, body = null) {
  const url = `https://${host}:${API_PORT}${path}`;
  const headers = {
    'X-Api-Key': key,
    'Content-Type': 'application/json',
  };

  try {
    const response = await axios({
      method,
      url,
      headers,
      data: body || {},
      timeout: 10000,
      httpsAgent,
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(`API Error: ${error.response.status} - ${JSON.stringify(error.response.data)}`);
    }
    throw error;
  }
}

/**
 * Main application logic
 */
async function main() {
  const args = process.argv.slice(2);
  if (args.length < 3) {
    console.log(`Usage: node index.js <display-ip> <filename> <api-key> [show-in-archive]`);
    process.exit(1);
  }

  const [host, filename, key, targetShow] = args;

  if (!fs.existsSync(filename)) {
    console.error(`Error: File '${filename}' not found.`);
    process.exit(1);
  }

  // 1. Read and encode file
  console.log(`Reading '${filename}'...`);
  const fileBuffer = fs.readFileSync(filename);
  const b64Data = fileBuffer.toString('base64');

  // 2. Upload to library
  console.log(`Uploading to ${host}:${API_PORT}...`);
  let showName;
  try {
    const uploadResult = await api(host, key, 'POST', '/api/library/upload', {
      name: path.basename(filename),
      data: b64Data,
    });
    console.log(`Upload successful: ${uploadResult.name}`);
    showName = uploadResult.name;
  } catch (err) {
    console.error(`Upload failed: ${err.message}`);
    process.exit(1);
  }

  // 3. Resolve start name (strip extension)
  let startName = showName;
  if (startName.endsWith('.ddl.json')) {
    startName = startName.slice(0, -9);
  } else if (startName.endsWith('.json')) {
    startName = startName.slice(0, -5);
  }

  // 4. Stop current show
  console.log(`Ensuring server is ready...`);
  try {
    await api(host, key, 'POST', '/api/show/stop');
  } catch (e) {
    // Ignore if no show was playing
  }

  // 5. Start playback
  let msg = `Starting show '${startName}'`;
  if (targetShow) msg += ` (internal show: ${targetShow})`;
  console.log(`${msg}...`);

  try {
    const payload = { name: startName };
    if (targetShow) payload.show = targetShow;

    const result = await api(host, key, 'POST', '/api/show/start', payload);
    const actualName = result.name || `${result.archive} [${result.show}]`;
    console.log(`Playback started: ${actualName}`);
  } catch (err) {
    console.error(`Failed to start show: ${err.message}`);
    process.exit(1);
  }

  console.log('\nControls:  \u2190 (left) previous  |  \u2192 (right) next  |  c clear cache  |  q quit\n');

  // Setup keypress listener
  readline.emitKeypressEvents(process.stdin);
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(true);
  }

  process.stdin.on('keypress', async (str, keyPress) => {
    try {
      if (keyPress.name === 'left') {
        await api(host, key, 'POST', '/api/show/previous');
        process.stdout.write('\u2190 previous\n');
      } else if (keyPress.name === 'right') {
        await api(host, key, 'POST', '/api/show/next');
        process.stdout.write('\u2192 next\n');
      } else if (keyPress.name === 'c' && !keyPress.ctrl) {
        await api(host, key, 'POST', '/api/cache/clear');
        process.stdout.write('cache cleared\n');
      } else if (keyPress.name === 'q' || (keyPress.ctrl && keyPress.name === 'c')) {
        console.log('Stopping show...');
        await api(host, key, 'POST', '/api/show/stop');
        console.log('Done.');
        process.exit();
      }
    } catch (err) {
      console.error(`Error during control: ${err.message}`);
    }
  });
}

main().catch((err) => {
  console.error(`Unhandled error: ${err.message}`);
  process.exit(1);
});
