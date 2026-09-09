const fields = [
  'school_id', 'school_name', 'school_name_cn', 'short_name',
  'school_type', 'city', 'city_cn', 'state', 'location_cn', 'region',
  'tuition', 'tuition_year', 'coa', 'coa_year', 'first_year_enrollment',
  'international_pct', 'campus_type', 'campus_description',
  'campus_description_cn', 'famous_majors', 'famous_majors_cn',
  'career_model', 'career_model_cn', 'notable_alumni',
];

// Bounded streaming read; Content-Length alone cannot enforce the limit.
async function readBody(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error('Missing body');
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 1024) {
        await reader.cancel();
        throw new Error('Body too large');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}

export function createHandler({ getEnv, fetchImpl = fetch }) {
  return async (request) => {
    const headers = {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Vary': 'Origin',
    };
    const origin = request.headers.get('origin');
    const allowedOrigin = getEnv('ALLOWED_ORIGIN') || 'https://mingligraphics.github.io';
    if (origin === allowedOrigin) {
      headers['Access-Control-Allow-Origin'] = origin;
      headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS';
      headers['Access-Control-Allow-Headers'] = 'content-type, authorization, apikey, x-client-info';
    }
    const json = (status, body) => new Response(JSON.stringify(body), { status, headers });
    const error = (status, message) => json(status, { error: message });

    // OPTIONS is a CORS handshake only; it never reads protected data.
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    if (request.method !== 'POST') {
      headers.Allow = 'POST, OPTIONS';
      return error(405, 'Use POST');
    }
    if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
      return error(400, 'Content-Type must be application/json');
    }
    let body;
    try {
      body = await readBody(request);
    } catch {
      return error(400, 'Invalid JSON body or body exceeds 1024 bytes');
    }
    if (!body || Array.isArray(body) || typeof body !== 'object' ||
        Object.keys(body).length !== 2 ||
        typeof body.schoolA !== 'string' || typeof body.schoolB !== 'string') {
      return error(400, 'Provide only schoolA and schoolB as strings');
    }
    const { schoolA, schoolB } = body;
    const validId = (id) => id.length <= 100 && /^[a-z0-9][a-z0-9_-]*$/.test(id);
    if (!validId(schoolA) || !validId(schoolB) || schoolA === schoolB) {
      return error(400, 'Provide two distinct, nonblank school IDs in canonical format');
    }
    try {
      const url = getEnv('SUPABASE_URL');
      let keys;
      try {
        keys = JSON.parse(getEnv('SUPABASE_SECRET_KEYS') || 'null');
      } catch {
        return error(500, 'Server configuration error');
      }
      const key = keys && typeof keys === 'object' && !Array.isArray(keys)
        ? keys.default : undefined;
      if (!url || typeof key !== 'string' || !key.trim()) {
        return error(500, 'Server configuration error');
      }
      const response = await fetchImpl(`${url.replace(/\/$/, '')}/rest/v1/rpc/get_school_comparison`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Profile': 'public',
          'apikey': key,
        },
        body: JSON.stringify({ p_school_id_a: schoolA, p_school_id_b: schoolB }),
        signal: AbortSignal.timeout(10000),
        redirect: 'error',
      });
      const data = await response.json();
      if (!response.ok) {
        if (data?.code === 'P0002') return error(404, 'One or both schools do not exist');
        if (data?.code === '22023') return error(400, 'Invalid school IDs');
        return error(500, 'Comparison unavailable');
      }
      if (!Array.isArray(data) || data.length !== 2 ||
          data[0]?.school_id !== schoolA || data[1]?.school_id !== schoolB ||
          data.some((row) => fields.some((field) => !Object.hasOwn(row, field)))) {
        return error(500, 'Unexpected comparison response');
      }
      // Explicit response allowlist protects against future RPC additions.
      return json(200, data.map((row) => Object.fromEntries(fields.map((field) => [field, row[field]]))));
    } catch {
      // Never return or log database messages, request headers, or credentials.
      return error(500, 'Comparison unavailable');
    }
  };
}
