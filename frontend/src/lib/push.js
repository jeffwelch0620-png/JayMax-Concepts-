import * as api from "./api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

// Registers the service worker (idempotent) and subscribes this device to
// web push for the given restaurant, so managers can push count/prep tasks.
export async function enablePushNotifications(rid, pin) {
  if (!pushSupported()) throw new Error("Push notifications aren't supported on this device");
  const { publicKey, enabled } = await api.pushPublicKey(rid);
  if (!enabled || !publicKey) throw new Error("Push notifications aren't configured for this restaurant yet");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications permission was not granted");
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  }
  const json = sub.toJSON();
  await api.pushSubscribe(rid, { pin, endpoint: json.endpoint, keys: json.keys });
  return sub;
}

export async function disablePushNotifications(rid, pin) {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  const endpoint = sub.endpoint;
  await sub.unsubscribe();
  await api.pushUnsubscribe(rid, { pin, endpoint });
}

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`${process.env.PUBLIC_URL}/service-worker.js`).catch(() => { /* PWA is a progressive enhancement */ });
  });
}
