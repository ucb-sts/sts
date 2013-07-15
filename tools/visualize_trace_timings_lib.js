// This file contains commonly used functions for display tools

var tooltip = {};
var nullData = [
  {times: []}
];
var width = 4000;
var charts = [];
var svgs = [];

function initFileUpload(elementId, svg, chart, primaryChart, timeline_type) {
  var upload = document.getElementById(elementId);

  if (typeof window.FileReader === 'undefined') {
    alert("File API Not Supported");
  }

  upload.onchange = function (e) {
    e.preventDefault();

    var file = upload.files[0],
        reader = new FileReader();

    reader.onload = function (event) {
      var data = formatData(event.target.result);

      if (timeline_type == "1d"){
        data = applyOffset(data);
      }

      timelineCircle(svg, chart, data);
    };
    reader.readAsText(file);

    return false;
  };
}

// When an auxiliary chart is loaded, compute an offset in milliseconds from
// the primary chart.
function computeOffset(auxiliaryData, startingTimes) {
  // units are milliseconds
  for (i = 0; i < auxiliaryData.length/6; i++){
    // start each timeline at it's own time, zeroing the time of the first event
    var min = 10000000000000;
    for (j = i*6; j < i*6+5; j++){
      if (auxiliaryData[j]["times"].length > 0){
        min = Math.min( min, auxiliaryData[j]["times"][0]["starting_time"] );
      }
    }
    startingTimes.push(min);
  }
}

function applyOffset(data) {
  var startingTimes = [];
  computeOffset(data, startingTimes);
  for (i = 0; i < data.length/6; i++){ // timeline num
    for (j = i*6; j < i*6+5; j++){ // each row for the corresponding timeline
      for (k = 0; k < data[j]["times"].length; k++){ // each event in the row
        data[j]["times"][k]["starting_time"] -= startingTimes[i];
        data[j]["times"][k]["ending_time"] -= startingTimes[i];
      }
    }
  }
  return data;
}

function timelineCircle(svg, chart, data) {
  svg.datum(data).call(chart);

}

// appendElementToDOM currently only supports two types of elements:
// file uploads and charts
function appendElementToDOM(type, element){
  if (type === "file upload"){
    var p = document.createElement('p');
    var input = document.createElement('input');
    input.setAttribute('type', 'file');
    input.setAttribute('id', element);
    p.appendChild(input);
    document.body.appendChild(p);
  } else if (type === "chart"){
    var div = document.createElement('div');
    div.setAttribute('id', element);
    document.body.appendChild(div);
  }
}

function appendToDOM(fileElement, chartElement, timeline_type) {
  // the order in which elements are currently displayed
  if (timeline_type == "1d"){
    for (i = 0; i < fileElement.length; i++){
      appendElementToDOM("file upload", fileElement[i]);
    }
  }
  else if (timeline_type == "2d"){
    appendElementToDOM("file upload", fileElement);
  }

  appendElementToDOM("chart", chartElement);
}

window.onload = function() {
  tooltip = Tooltip("vis-tooltip", 230);
  appendChart(nullData);
}

// Mouseover callback
showDetails = function(d, i, datum, IDs, g, timeline_type) {
  var content;
  content = '<p class="main">' + d.label + '</span></p>';
  content += '<hr class="tooltip-hr">';
  content += '<p class="main">' + d.class + '</span></p>';
  content += '<p class="main">Time (ms): ' + d.starting_time + '</span></p>';
  tooltip.showTooltip(content, d3.event);

  if (timeline_type == "1d"){
    // show functional equivalence lines when the user mouses over the event
    if (IDs[d.fe_id].length >= 4){
      for ( i = 0; i < IDs[d.fe_id].length-2; i+=2) {
        g.append('line')
          .attr("x1", IDs[d.fe_id][i])
          .attr("y1", IDs[d.fe_id][i+1])
          .attr("x2", IDs[d.fe_id][i+2])
          .attr("y2", IDs[d.fe_id][i+3])
          .style("stroke","rgb(255,0,0)");
      }
    }
  }
};

// Mouseout callback
hideDetails = function(d, i, datum, IDs, g, timeline_type) {
  tooltip.hideTooltip();

  if (timeline_type == "1d"){
    // remove functional equivalence lines after the user mouses over the event
    lines = g.selectAll("line");
    lastElement = lines[0].length-1;
    for ( i = 0; i < IDs[d.fe_id].length/2; i++){
      lines[0][lastElement-i].remove();
    }
  }
};

function pushChart(data, index, fileElement, chartElement, timeline_type){
  charts.push(d3.timeline(timeline_type)
    .stack()
    .tickFormat(
      {format: d3.time.format("%M:%S:%L"),
      tickTime: d3.time.seconds,
      tickNumber: 3,
      tickSize: 30})
    .rotateTicks(45)
    .display("circle") // toggle between rectangles and circles
    .mouseover(showDetails)
    .mouseout(hideDetails));
  svgs.push(d3.select("#" + chartElement).insert("svg").attr("width", width));
  timelineCircle(svgs[index], charts[index], data);

  for (i = 0; i < fileElement.length; i++){
    initFileUpload(fileElement[i], svgs[index], charts[index], true, timeline_type);
  }
}


