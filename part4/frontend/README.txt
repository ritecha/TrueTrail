TrueTrail theme + layout fix  (only the changed files; same folder structure as part4/frontend)

COPY these over your project (part4/frontend/src/...):
  src/theme.css            NEW   <- all dark + light colours, left rail, graph/timeline split
  src/index.css            1 line changed (html background)
  src/App.jsx              theme.css import, toggle moved into the left rail
  src/investigators.js     passwords removed; name directory for Clerk users
  src/store.js             evidence rows always get id/uid/sha/ts (fixes React key warning)
  src/components/Header.jsx            now the left navigation rail
  src/components/Workspaces.jsx        sample case visible to every signed-in user
  src/components/WorkspaceView.jsx     Graph tab = timeline (left) + graph (right)
  src/components/GroupChat.jsx         names via nameOf()
  src/components/GraphView.jsx         theme-aware canvas + "Search from graph"
  src/components/TimeMap.jsx           map background uses theme variable

DELETE:  src/components/Login.jsx   (old password login, unused since Clerk)
OPTIONAL: delete the "Light Theme Overrides" block at the end of src/App.css (theme.css replaces it)
Timeline files (TimeMap.jsx logic, timeline.json) are NOT changed apart from the map background colour.
