// Fetch JSON from the backend; throws an Error with the API's detail message on failure.
export async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join("; ") : data?.detail;
    throw new Error(detail || `Request failed (${response.status}).`);
  }
  return data;
}

// POST one file as multipart form data.
export function uploadFile(url, file) {
  const body = new FormData();
  body.append("file", file);
  return requestJson(url, { method: "POST", body });
}
