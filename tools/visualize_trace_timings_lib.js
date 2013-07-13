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



