// Minimal text-only WebSocket client used by netplay.c.
//
//   Windows     WinHTTP (built in): ws:// and wss://           link -lwinhttp
//   Emscripten  the browser's WebSocket: ws:// and wss://      link -lwebsocket.js
//   Linux/macOS plain sockets: ws://; wss:// with -DNETPLAY_OPENSSL and -lssl -lcrypto
//
// Everything is non-blocking except the DNS lookup: call NpWs_Poll each frame.
#ifndef NETPLAY_WS_H
#define NETPLAY_WS_H
#include <stdbool.h>

typedef struct NpWs NpWs;

typedef enum { NPWS_CONNECTING = 0, NPWS_OPEN, NPWS_CLOSED } NpWsState;

NpWs *NpWs_Open(const char *url);          // NULL only for a malformed URL
NpWsState NpWs_Poll(NpWs *ws);             // advances the connection; returns the state
bool NpWs_Send(NpWs *ws, const char *text, int len);
int  NpWs_Recv(NpWs *ws, char **msg);      // one whole text message (caller frees), 0 = none
const char *NpWs_Error(const NpWs *ws);    // why it closed ("" if it didn't)
void NpWs_Close(NpWs *ws);                 // closes and frees

#endif
