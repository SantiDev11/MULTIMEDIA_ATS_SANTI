
cbuffer CursorCB : register(b0) {
  float4 cursorData;
  float4 rtData;
};
// ROADWORKS CURSOR: flecha con franjas de obra. La punta es (0,0) = hotspot
// exacto. Color interior configurable (mouse_color).
static const float2 P[7]={float2(0,0),float2(0,2.42),float2(0.62,1.80),
 float2(1.02,2.74),float2(1.48,2.54),float2(1.08,1.62),float2(1.76,1.58)};
float4 main(float4 pos : SV_Position) : SV_Target {
  float s = max(cursorData.z, 5.0) * 1.15;
  float2 p = (pos.xy - cursorData.xy) / s;
  float d = 1e9, sg = 1.0;
  [unroll] for (int i = 0; i < 7; i++) {
    float2 a = P[i], e = P[(i+1)%7] - a, w = p - a;
    float2 q = w - e * saturate(dot(w,e) / dot(e,e));
    d = min(d, dot(q,q));
    bool3 b = bool3(p.y >= a.y, p.y < a.y + e.y, e.x*w.y > e.y*w.x);
    if (all(b) || all(!b)) sg = -sg;
  }
  d = sqrt(d)*sg*s;            // distancia con signo, en pixeles
  clip(0.9 - d);               // fuera de la flecha no se graba nada
  float bw = s * 0.17;         // grosor del contorno oscuro
  float ini = 1.0 - smoothstep(-0.9, 0.9, d);
  float nuc = 1.0 - smoothstep(-bw - 0.6, -bw + 0.6, d);
  float t = abs(frac((p.x - p.y) * 1.15) * 2.0 - 1.0);
  float3 c = float3(cursorData.w, rtData.z, rtData.w);
  c = lerp(c * 0.14, c, smoothstep(0.42, 0.58, t));
  c = lerp(0.05, c, nuc);
  return float4(c, lerp(0.88, 0.96, nuc) * ini);
}
