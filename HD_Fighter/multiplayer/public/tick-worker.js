// Runs while the tab is in the background. rAF is throttled there; this is not.
setInterval(() => postMessage(Date.now()), 50);
