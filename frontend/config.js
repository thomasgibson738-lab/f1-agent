// Backend API base URL.
//
// Local dev: the FastAPI server on localhost:8000.
// Production: your Render service URL, e.g. https://f1-agent-api.onrender.com
//
// The frontend auto-selects: localhost when opened locally, otherwise the
// production URL below. Edit PROD_API_BASE once your Render service is live.
const PROD_API_BASE = "https://f1-agent-api.onrender.com";

const API_BASE =
  location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : PROD_API_BASE;
