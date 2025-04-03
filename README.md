# caldav-to-ics
A Next.js and Python calendar tool that syncs with CalDAV server and exports events to one ICS file.

## Context
If you have a CalDAV server and would like to sync events to Google Calendar or others for streamlined calendar management, you don't have many choices - iOS/macOS support CalDAV but only for local usage; DAVx5 requires you to keep running an Android application.

For jobs like scheduled calendar event synchronization, something that can be run on the server would be the ideal solution. This project provides a tool that runs on the server for syncing between CalDAV servers and ICS format, which can then be imported to various calendar services.

This tool can be easily deployed to cloud platforms like Vercel, or you can containerize it with Docker for deployment on your home server.

## Usage
The tool allows you to:
- Connect to a CalDAV calendar server
- Export events to ICS format
- Upload/update to an ICS file on cloud storage (Vercel Blob in current code)
- Get a URL to the ICS file and subscribe to it in Google Calendar or use scripts like [GAS-ICS-Sync](https://github.com/derekantrican/GAS-ICS-Sync)
> *Note: For security reasons, you need to get the URL from cloud storage manually.*
- Scheduled synchronization (currently runs once per day due to Vercel free tier limitations, configurable in `vercel.json`)
- A simple interface to check last sync time and trigger manual synchronization

![Screenshot of User Interface](https://github.com/user-attachments/assets/9bf0945d-006d-4fe4-b16c-c979358753fd)

### Example
For Lark/Feishu calendar users, you can retrieve CalDAV server details from the desktop application and use this tool to create an ICS file that you can then subscribe to in Google Calendar.

## Run Locally

- Clone this repo
- Add local environment variables by copying the `.env.example` file and enter values:
 
| Variable | Description |
 |--------|------|
 | `BLOB_READ_WRITE_TOKEN` | Your Vercel Blob token |
 | `BLOB_PATH` | Path to the ICS file on your Vercel Blob |
 | `CALDAV_URL` | CalDAV server url |
 | `CALDAV_USERNAME` | CalDAV server username |
 | `CALDAV_PASSWORD` | CalDAV server password |

- Install the dependencies:

```bash
pnpm install
```

- Virtual Python environment if needed:

```bash
python3 -m venv venv
source venv/bin/activate
```

- Run the development server:

```bash
pnpm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser to see the result.

The Flask servers will provide API on `http://127.0.0.1:5328/api/sync` – feel free to change the port in `package.json` (you'll also need to update it in `next.config.js`).

## Deploy to Vercel
- Clone this repo and deploy on Vercel
- Enable and connect Vercel Blob, create ICS file in the Blob
- Add Environment Variables in project settings: `BLOB_PATH`, `CALDAV_URL`, `CALDAV_USERNAME` and `CALDAV_PASSWORD`
- Re-deploy and visit project domain to see the result

## Tech Stack
- Next.js as the frontend
- Python/Flask server hosted as [Python serverless functions](https://vercel.com/docs/concepts/functions/serverless-functions/runtimes/python), as the backend API
- Python packages:
  - [caldav](https://github.com/python-caldav/caldav): Connect and get events from CalDAV server
  - [icalendar](https://github.com/collective/icalendar): Process ICS format

## Acknowledgements
- https://xuanwo.io/reports/2023-35/
- https://jia.je/software/2025/02/04/feishu-dump-calendar/
- https://github.com/python-caldav/caldav/issues/459 - for fixing caldav's compatibility issue with Lark/Feishu's CalDAV server
