/*-----------------------------------------------------*
 *            Globally accessible variables            *
 *-----------------------------------------------------*/

var globals = {
  initialTraceCount: 2,        // How many event.traces to display
  baseTimelineWidth: 1000,     // Base width of timeline width, not subject to zooming
  timelineType: "1d",          // "1d" or "2d"
  timeline: null,
  tooltip: null,
  traceCount: 0
}

function setTimelineType(type)
{
  if (type!="1d" && type!="2d") {
    throw "Unsupported timeline type "+type+"!";
  }
  globals.timelineType = type;
}

function setInitialTraceCount(count)
{
  if (count < 1 || count > 10) {
    throw "Choose an initial trace count between 1 and 10!";
  }
  globals.initialTraceCount = count;
}

function setBaseTimelineWidth(baseWidth)
{
  if (width < 0 || width > 10000) {
    throw "Choose a base timeline width between 0 and 10000!"
  }
  globals.baseTimelineWidth = baseWidth;
}

/*-----------------------------------------------------*
 *                 DOM utility functions               *
 *-----------------------------------------------------*/

// Create a d3 timeline, and append its SVG to DOM
function appendTimeline()
{
  $("#timeline-container").append(
    $("<div>", {
      id: "timeline"
    })
  );
  setTimeline();
  d3.select("#timeline").insert("svg")
                        .attr("height", 3000)
                        .attr("width", globals.baseTimelineWidth);
  drawBlankTimeline();
}

// Create and initialize a file uploader, and append to DOM
function appendFileUploader()
{
  var uploader = $("<input>", {
                   type: "file",
                   class: "uploader",
                   id: "uploader"+globals.traceCount,
                 }).appendTo("#uploader-container");
  initializeFileUploader();
  globals.traceCount++;
}

// Remove a file uploader from DOM
function removeFileUploader()
{
  $("#uploader"+(globals.traceCount-1)).remove();
  globals.traceCount--;
}

// Set callbacks for the latest file uploader
function initializeFileUploader()
{
  var index = globals.traceCount;
  var uploader = document.getElementById("uploader"+index);
  uploader.onchange = (function (e)
  {
    e.preventDefault();
    var file = uploader.files[0];
    if (file) {
      var reader = new FileReader();
      reader.readAsText(file);
      reader.onload = function (e) {
        var data = null;
        if (globals.timelineType == "1d") {
          data = formatData1D(event.target.result);
        } else if (globals.timelineType == "2d") {
          data = formatData2D(event.target.result);
        } else {
          throw "Unknown timeline type: "+globals.timelineType;
        }
        drawData(data);
      }
    }
  }).bind(this);
}

// Append buttons that change the number of file uploaders to DOM
function appendPlusMinusButtons()
{
  $("<input>", {
    type: "button",
    value: "+",
    click: appendFileUploader
  }).appendTo("#tuner-container");
  $("<input>", {
    type: "button",
    value: "-",
    click: removeFileUploader
  }).appendTo("#tuner-container");
}

/*-----------------------------------------------------*
 *                   Library functions                 *
 *-----------------------------------------------------*/

function setTimeline()
{
  var t = d3.timeline(globals.timelineType)
    .stack()
    .tickFormat({
      format: d3.time.format("%M:%S:%L"),
      tickTime: d3.time.seconds,
      tickNumber: 3,
      tickSize: 30
     })
    .rotateTicks(45)
    .display("circle") // toggle between rectangles and circles
    .mouseover(showDetails)
    .mouseout(hideDetails);
  globals.timeline = t;
}

function drawBlankTimeline() {
  drawData([
    { times: [] }
  ]);
}

function drawData(data) {
  d3.select("#timeline svg").datum(data).call(globals.timeline);
}

function setTooltip() {
  globals.tooltip = Tooltip("vis-tooltip", 230);
}

// Mouseover callback for each timeline event 
function showDetails(d, i, datum, IDs)
{
  var content = '<p class="main">' + d.label + '</span></p>';
  content += '<hr class="tooltip-hr">';
  content += '<p class="main">' + d.class + '</span></p>';
  content += '<p class="main">Time (ms): ' + d.starting_time + '</span></p>';
  globals.tooltip.showTooltip(content, d3.event);
  if (globals.timelineType == "1d") {
    // show functional equivalence lines when the user mouses over the event
    if (IDs[d.fe_id].length >= 4) {
      for (var i = 0; i < IDs[d.fe_id].length-2; i += 2) {
        d3.select("#timeline svg").append('line')
          .attr("x1", IDs[d.fe_id][i])
          .attr("y1", IDs[d.fe_id][i+1])
          .attr("x2", IDs[d.fe_id][i+2])
          .attr("y2", IDs[d.fe_id][i+3])
          .style("stroke","rgb(255,0,0)");
      }
    }
  }
}

// Mouseout callback for each timeline event 
function hideDetails (d, i, datum, IDs)
{
  globals.tooltip.hideTooltip();
  if (globals.timelineType == "1d") {
    // remove functional equivalence lines after the user mouses over the event
    lines = d3.select("#timeline svg").selectAll("line");
    lastElement = lines[0].length-1;
    for (var i = 0; i < IDs[d.fe_id].length/2-1; i++) {
      lines[0][lastElement-i].remove();
    }
  }
}

/*-----------------------------------------------------*
 *                 Data utility functions              *
 *-----------------------------------------------------*/

var invariantViolations = { "InvariantViolation" : true };
var internalEvents = {
  "ControlMessageReceive" : true,
  "ControlMessageSend"    : true,
  "ConnectToControllers"  : true,
  "ControllerStateChange" : true,
  "DeterministicValue"    : true,
  "DataplanePermit"       : true
};

// The key is the timeline index, and the value
var data_timeline = {};
// timeline_num is a counter tracking what chart we are currently loading:
// the first time we load this is set to 1, and incremented for
// every subsequent load.
var timeline_num = 0;
// stores the results for formatData
var result_timeline = {};
// stores of the fe_id for all events
var All_Events_Hash = {};
// keeps track of the next available fe_id to be assigned to a new event
var new_event_count = 0;
var timedelayms = 6; // chosen arbitrarily

function formatData1D(data)
{
  timeline_num++;
  prepData(data, timeline_num);
  processTimelineData(timeline_num, result_timeline);
  return formatDataResult1D(result_timeline);
}

function prepData(data, timeline_num)
{
  // Store arrays of raw json strings until both charts are loaded.
  data_timeline[timeline_num] = data.split("\n");
  All_Events_Hash[timeline_num] = [];
  result_timeline[timeline_num] = { "internal": [], "input": [], "timed out": [], "new internal": [], "violation": []};
}

function formatDataResult1D(result_timeline)
{
  var result = [];
  for (var timeline_id in result_timeline) {
    for (var times in result_timeline[timeline_id]) {
      var s = {};
      s["label"] = "" + times;
      s["times"] = result_timeline[timeline_id][times];
      result.push(s);
    }
    var s = {};
    s["label"] = "";
    s["times"] = [];
    result.push(s);
  }
  return applyOffset(result);
}

// When an auxiliary chart is loaded, apply an offset in milliseconds from the primary chart.
function applyOffset(data)
{
  var startingTimes = [];
  computeOffset(data, startingTimes);
  for (var i = 0; i < data.length/6; i++) { // timeline num
    for (var j = i*6; j < i*6+5; j++) { // each row for the corresponding timeline
      for (var k = 0; k < data[j]["times"].length; k++) { // each event in the row
        data[j]["times"][k]["starting_time"] -= startingTimes[i];
        data[j]["times"][k]["ending_time"] -= startingTimes[i];
      }
    }
  }
  return data;
}

function computeOffset(auxiliaryData, startingTimes)
{
  // units are milliseconds
  for (var i = 0; i < auxiliaryData.length/6; i++) {
    // start each timeline at it's own time, zeroing the time of the first event
    var min = Number.MAX_VALUE;
    for (var j = i*6; j < i*6+5; j++) {
      if (auxiliaryData[j]["times"].length > 0) {
        min = Math.min( min, auxiliaryData[j]["times"][0]["starting_time"] );
      }
    }
    startingTimes.push(min);
  }
}

function processTimelineData(timelineNum, result_timeline)
{
  var data = data_timeline[timelineNum];
  var start_position = 0;
  for (var i = 0; i < data.length-1; i++) {
    var str = data[i];
    var e = jQuery.parseJSON(str);
    var time_key = "time";
    if ("replay_time" in e) {
      time_key = "replay_time";
    }
    var epochMillis = (e[time_key][0] * 1000) + (e[time_key][1] / 1000);
    var e_id;
    if (timelineNum == 1) {
      // arbitrary id that is simply its position in the event list of timeline1
      e_id = new_event_count;
      new_event_count++;
    } else {
      // id that corresponds to its functionally equivalent event in timeline1
      e_id = findFunctionallyEquivalentEventID(e, start_position, timeline_num);
      // update the starting position for the next event (to keep relative ordering correct)
      if (e_id != -1) {
        start_position = e_id+1;
      } else {
        // did not find a functionally equivalent event, therefore assign a new fe_id
        e_id = new_event_count;
        new_event_count++;
      }
    }
    var point = {"starting_time": epochMillis,
                 "ending_time": epochMillis,
                 "label": e["label"],
                 "class": e["class"],
                 "fe_id": e_id};
    All_Events_Hash[timeline_num].push(e_id);
    // Demultiplex by element["class"] for internal vs. input
    var eventClass = e["class"];
    if (eventClass === "InvariantViolation") {
      result_timeline[timeline_num]["violation"].push(point);
    } else if (eventClass in internalEvents)  {
      if ("timed_out" in e && e["timed_out"]) {
        result_timeline[timeline_num]["timed out"].push(point);
      } else if ("new_internal_event" in e && e["new_internal_event"]) {
        result_timeline[timeline_num]["new internal"].push(point);
      } else {
        result_timeline[timeline_num]["internal"].push(point);
      }
    } else {
      result_timeline[timeline_num]["input"].push(point);
    }
  }
}

/* 
 * findFunctionallyEquivalentEventID takes an event from timeline_num and
 * returns the ID of its functional equivalent in the first loaded timeline, 
 * or -1 if no functional equivalent event exists. Comparisons are always 
 * made to the original loaded trace. 
 * 
 * An event e2 from a replay run is functionally equivalent to an event e1 from
 * the original run iff their fingerprints are the same, and:
 *  - let p2 denote the predecessor of e2
 *  - let s2 denote the successor of e2
 *  - let p1 denote p2's functional equivalent from the original run
 *  - let s1 denote s2's functional equivalent from the original run
 * then e1 must occur between p1 and s1.
 * 
 * In other words, the two events should be in the same relative position in the
 * log. In practice we keep track of relative position by looking for the fe_id
 * of the event right before, and then searching for an fe_id that is the largest
 * smaller fe_id than that.
 */
function findFunctionallyEquivalentEventID(e, startPos, timeline_num)
{
  for (var t_num = 1; t_num < timeline_num; t_num++) {
    for (var i_old = startPos; i_old < data_timeline[t_num].length-1; i_old++) {
      var str_old = data_timeline[t_num][i_old];
      var e_old = jQuery.parseJSON(str_old);
      // using JSON.stringify() to compute .equals() for objects/arrays in fingerprint
      if (JSON.stringify(e_old["fingerprint"]) === JSON.stringify(e["fingerprint"])) {
        return All_Events_Hash[t_num][i_old];
      }
    }
  }
  return -1;
}

function formatData2D(data)
{
  var split = data.split("\n");
  var entities = findEntities(split);
  for (var i = 0; i < split.length-1; i++) {
    var str = split[i];
    var e = jQuery.parseJSON(str);
    var time_key = "time";
    if ("replay_time" in e) {
      time_key = "replay_time";
    }
    var epochMillis = (e[time_key][0] * 1000) + (e[time_key][1] / 1000);
    var point = {"starting_time": epochMillis,
                 "ending_time": epochMillis,
                 "label": e["label"],
                 "class": e["class"],
                 "sr_id": i};
    processEvent(e, point, entities);
  }
  return formatDataResult2D(entities);
}

// Find all controllers, switches, and hosts in data
function findEntities(data)
{
  var entities = {"controllers":{}, "switches":{}, "hosts":{}};
  for (var i = 0; i < data.length-1; i++) {
    var e = jQuery.parseJSON(data[i]);
    var eventHandlerMap = {
      "ControllerStateChange" : [findController],
      "ControllerFailure"     : [findController],
      "ControllerRecovery"    : [findController],
      "ControlMessageSend"    : [findController, findSwitch],
      "ControlMessageReceive" : [findController, findSwitch],
      "TrafficInjection"      : [findHost],
      "HostMigration"         : [findHost],
      "DataplaneDrop"         : [findSwitch, findHost]
    }
    if (e.class in eventHandlerMap) {
      var eventHandlers = eventHandlerMap[e.class];
      for (var j = 0; j < eventHandlers.length; j++) {
        eventHandlers[j]();
      } 
    }
  }

  function findController() {
    if (!(e["controller_id"] in entities["controllers"])) {
      entities["controllers"][e["controller_id"]] = [];
    }
  }

  function findSwitch() {
    if (!(e["dpid"] in entities["switches"])) {
      entities["switches"][e["dpid"]] = [];
    }
  }

  function findHost() {
    if (!(e["host_id"] in entities["hosts"])) {
      entities["hosts"][e["host_id"]] = [];
    }
  }
  return entities;
}

function processEvent(e, point, entities, i)
{
  // Demultiplex by e["class"] for displaying events on corresponding entities
  var eventClass = e["class"];
  var eventHandlerMap = {
    "ConnectToControllers"     : processConnectToControllers,
    "ControllerStateChange"    : processControllerStateChange,
    "ControllerFailure"        : processControllerFailureRecovery,
    "ControllerRecovery"       : processControllerFailureRecovery,
    "ControllerChannelBlock"   : processControllerChannelBlockUnblock,
    "ControllerChannelUnblock" : processControllerChannelBlockUnblock,
    "ControlMessageSend"       : processControlMessageSendReceive,
    "ControlMessageReceive"    : processControlMessageSendReceive,
    "LinkFailure"              : processLinkFailureRecovery,
    "LinkRecovery"             : processLinkFailureRecovery,
    "TrafficInjection"         : processTrafficInjection,
    "HostMigration"            : processHostMigration,
    "DataplaneDrop"            : processDataplaneDrop,
    "DataplanePermit"          : processDataplanePermit
  } 
  if (eventClass in eventHandlerMap) {
    eventHandlerMap[eventClass]();
  }

  // Display event on all controllers and switches
  function processConnectToControllers() {
    for (var id in entities["controllers"]) {
      addEvent("controllers", id, point, entities);
    }
    for (var id in entities["switches"]) {
      addEvent("switches", id, point, entities);
    }
  }

  // Display event on corresponding controller
  function processControllerStateChange() {
    addEvent("controllers", e["controller_id"], point, entities);
  }

  // Display event on corresponding controller and switch
  function processControlMessageSendReceive() {
    // Include a 6ms visual lag for messages to reach recipient
    epochMillisDelay = point["starting_time"] + (eventClass === "ControlMessageSend" ? timedelayms : -timedelayms);
    var pointDelay = {"starting_time": epochMillisDelay,
                      "ending_time": epochMillisDelay,
                      "label": e["label"],
                      "class": eventClass,
                      "sr_id": point["sr_id"]};

    addEvent("switches", e["dpid"], point, entities);
    addEvent("controllers", e["controller_id"], pointDelay, entities);
  }

  // Display event on corresponding controller
  function processControllerFailureRecovery() {
    addEvent("controllers", e["controller_id"], point, entities);
  }

  // Display event on corresponding switch
  function processDataplaneDrop() { 
    if ("dpid" in e) { 
      addEvent("switches", e["dpid"], point, entities);
    } 
    else if ("host_id" in e) {
      addEvent("hosts", e["host_id"], point, entities);
    }
  }

  // Currently ignored
  function processDataplanePermit() {}

  // Display event on corresponding switch
  function processControllerChannelBlockUnblock() {
    addEvent("switches", e["dpid"], point, entities);
  }

  // Display event on corresponding switches
  function processLinkFailureRecovery() {
    addEvent("switches", e["start_dpid"], point, entities);
    addEvent("switches", e["end_dpid"], point, entities);
  }

  // Display event on corresponding switch
  function processSwitchFailureRecovery() { 
    addEvent("switches", e["dpid"], point, entities);
  }

  // Display event on corresponding host
  function processTrafficInjection() {
    addEvent("hosts", e["host_id"], point, entities);
  }

  // Display event on corresponding host and switches
  function processHostMigration() {
    addEvent("hosts", e["host_id"], point, entities);
  }
}

// Push event on to corresponding entity's timeline
function addEvent(type, id, point, entities) {
  entities[type][id].push(point);
}

// Format results appropriately, in the order of controllers, switches, then hosts
function formatDataResult2D(entities)
{
  var result = [];
  for (var ent in entities) {
    // get a list of sorted keys such that order is preserved during the display
    var list = Object.keys(entities[ent]).sort(function(a,b) {return a - b});
    for (var i = 0; i < list.length; i++ ) {
      var s = {};
      s["label"] = "" + ent + " " + list[i];
      s["times"] = entities[ent][list[i]];
      result.push(s);
    }
  }
  return result;
}

