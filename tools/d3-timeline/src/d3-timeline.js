(function() {

  // timeline_type currently only supports two types of timelines: 1d and 2d
  d3.timeline = function(timeline_type) {
    var DISPLAY_TYPES = ["circle", "rect"];

    var hover = function () {},
        mouseover = function () {},
        mouseout = function () {},
        click = function () {},
        scroll = function () {},
        orient = "bottom",
        width = null,
        height = null,
        tickFormat = { format: d3.time.format("%I %p"),
          tickTime: d3.time.hours,
          tickNumber: 1,
          tickSize: 6 },
        colorCycle = d3.scale.category20(),
        display = "rect",
        beginning = 0,
        ending = 0,
        margin = {left: 30, right:400, top: 30, bottom:1000},
        stacked = false,
        rotateTicks = false,
        itemHeight = 20,
        itemMargin = 5,
        timelineDiffHeight = 150;

    var eventColors = {"ConnectToControllers": colorCycle(0),
                      "ControllerStateChange": colorCycle(1), 
                      "ControlMessageSend": colorCycle(2),
                      "ControlMessageReceive": colorCycle(3),
                      "DataplaneDrop": colorCycle(4),
                      "TrafficInjection": colorCycle(5),
                      "HostMigration": colorCycle(6),
                      "LinkFailure": colorCycle(7),
                      "SwitchFailure": colorCycle(8),
                      "LinkRecovery": colorCycle(9),
                      "SwitchRecovery": colorCycle(10),
                      "ControllerFailure": colorCycle(11),
                      "ControllerRecovery": colorCycle(12),
                      "ControlChannelBlock": colorCycle(13),
                      "ControlChannelUnblock": colorCycle(14)};

    function timeline (gParent) {
      var g = gParent.append("g");
      var gParentSize = gParent[0][0].getBoundingClientRect();
      var gParentItem = d3.select(gParent[0][0]);

      var yAxisMapping = {},
          maxStack = 1,
          minTime = 0,
          maxTime = 0;

      // clear the canvas
      d3.selectAll("circle").remove();
      d3.selectAll("line").remove(); 
      d3.selectAll("text").remove();

      setWidth();

      var IDs = {}; // 1D : functionally equivalent event pairs
                    // 2D : send/receive control message event pairs
      var legendHeight = 0; // keep track of the last drawn entity's position in the graph to appropriately display the legend

      // check how many stacks we're gonna need
      // do this here so that we can draw the axis before the graph
      if (stacked || (ending == 0 && beginning == 0)) {
        g.each(function (d, i) {
          d.forEach(function (datum, index) {

            // create y mapping for stacked graph
            if (stacked && Object.keys(yAxisMapping).indexOf(index) == -1) {
              yAxisMapping[index] = maxStack;
              maxStack++;
            }

            // always look for beginning and ending times of all timelines
            datum.times.forEach(function (time, i) {
              if (time.starting_time < minTime || minTime == 0)
                minTime = time.starting_time;
              if (time.ending_time > maxTime)
                maxTime = time.ending_time;
            });
          });
        });

        beginning = minTime;
        ending = maxTime;
      }

      var scaleFactor = (1/(ending - beginning)) * (width - margin.left - margin.right);

      // draw the axis
      var xScale = d3.time.scale()
        .domain([beginning, ending])
        .range([margin.left, width - margin.right]);

      var xAxis = d3.svg.axis()
        .scale(xScale)
        .orient(orient)
        .tickFormat(tickFormat.format)
        .ticks(tickFormat.tickTime, tickFormat.tickNumber);

      g.append("g")
        .attr("class", "axis")
        .attr("transform", "translate(" + 80 +","+ 0+")")
        .call(xAxis);

      g.each(function(d, i) {
        d.forEach( function(datum, index){
          var data = datum.times;
          var hasLabel = (typeof(datum.label) != "undefined");

          g.selectAll("svg").data(data).enter()
            .append(display)
            .attr('x', getXPos)
            .attr("y", getStackPosition)
            .attr("width", function (d, i) {
              return (d.ending_time - d.starting_time) * scaleFactor;
            })
            .attr("cy", getStackPosition)
            .attr("cx", getXPos)
            .attr("r", itemHeight/5)
            .attr("height", itemHeight)
            .style("fill", getColor)
            .on("mousemove", function (d, i) {
              hover(d, index, datum);
            })
            .on("mouseover", function (d, i) {
              mouseover(d, i, datum, IDs, g, timeline_type); 
            })
            .on("mouseout", function (d, i) {
              mouseout(d, i, datum, IDs, g, timeline_type); 
            })
            .on("click", function (d, i) {
              click(d, index, datum);
            })
          ;

          // 1D: keeping track of functionally equivalent events fe_id 
          // 2D: keeping track of send/receive events sr_id  
          for (i = 0; i < data.length; i++){
            var id; 
            if (timeline_type == "1d"){ 
              id = data[i].fe_id;
            } 
            else if (timeline_type == "2d"){
              id = data[i].sr_id; 
            }

            if (!(id in IDs)){ 
              IDs[id] = [getXPos(data[i],i), getStackPosition(data[i],i)];
            } else {
              IDs[id].push(getXPos(data[i],i)); 
              IDs[id].push(getStackPosition(data[i],i));
            }
            
          }

          labelHeight = itemHeight/2 + margin.top + (itemHeight + itemMargin) * yAxisMapping[index]+ 25; 
          // update relative position of the legend 
          if ( labelHeight > legendHeight){
              legendHeight = labelHeight;
          }
          
          // add the label
          if (hasLabel) {
            gParent.append('text')
              .attr("class", "timeline-label")
              .attr("transform", "translate("+ 0 +","+ labelHeight+")")
              .text(hasLabel ? datum.label : datum.id);

              // 2D: draw the line for each entity beside the label
              if (timeline_type == "2d"){
                g.append("line")
                  .attr("x1", margin.left + 80)
                  .attr("y1", labelHeight - itemHeight/2)
                  .attr("x2", width - margin.right + 80)
                  .attr("y2", labelHeight - itemHeight/2)
                  .style("stroke","rgb(0,0,0)");
              }
          }

          if (typeof(datum.icon) != "undefined") {
            gParent.append('image')
              .attr("class", "timeline-label")
              .attr("transform", "translate("+ 0 +","+ labelHeight +")")
              .attr("xlink:href", datum.icon)
              .attr("width", margin.left)
              .attr("height", itemHeight);
          }

          function getStackPosition(d, i) {
            if (stacked) {
              return margin.top + (itemHeight + itemMargin) * yAxisMapping[index] + 25;
            }
            return margin.top + 25;
          }

          function getColor(d, i){
            if (d.class in eventColors){
              return eventColors[d.class];
            }
            return colorCycle(0);
          }
        });
      });

      // 2D: draw lines appropriately between send/receive messages between controllers and switches 
      if (timeline_type == "2d"){
        for (var id in IDs){
          if (IDs[id].length == 4){
            g.append('line')
              .attr("x1", IDs[id][0])
              .attr("y1", IDs[id][1])
              .attr("x2", IDs[id][2])
              .attr("y2", IDs[id][3])
              .style("stroke","rgb(0,0,0)");          
          }
        }
      }

      // draw legend after displaying trace 
      if (d3.selectAll("circle")[0].length != 0 ){
        gParent.append('text')
          .attr("class", "legend")
          .attr("transform", "translate(" + 20 + "," + (legendHeight+50) + ")")
          .style("font-size",13)
          .text("Legend");

        count = 0;
        eventsPerCol = 8;
        rowSpace = 18; 
        colSpace = 160;
        col = 0;

        // display event type and its corresponding color
        for(var e in eventColors){
          count++;
          if (count > col*eventsPerCol){
            col++;
          }
          gParent.append('circle')
            .attr('x', 40 + colSpace*(col-1))
            .attr("y", legendHeight + 47 + rowSpace*(count%(eventsPerCol)+1))
            .attr("cy", legendHeight + 47 + rowSpace*(count%(eventsPerCol)+1))
            .attr("cx", 40 + colSpace*(col-1))
            .attr("r", 3)
            .style("fill", eventColors[e]);   

          gParent.append('text')
            .attr("class", "legend")
            .attr("transform", "translate("+ (55 + colSpace*(col-1)) +","+ (legendHeight + 50 + rowSpace*(count%(eventsPerCol)+1))+")")
            .style("font-size",10.5)
            .text(e);
        }
      }


      if (width > gParentSize.width) {
        function move() {
          var x = Math.min(0, Math.max(gParentSize.width - width, d3.event.translate[0]));
          zoom.translate([x, 0]);
          g.attr("transform", "translate(" + x + ",0)");
          scroll(x*scaleFactor, xScale);
        }

        var zoom = d3.behavior.zoom().x(xScale).on("zoom", move);

        gParent
          .attr("class", "scrollable")
          .call(zoom);
      }

      if (rotateTicks) {
        g.selectAll("text")
          .attr("transform", function(d) {
            return "rotate(" + rotateTicks + ")translate("
              + (this.getBBox().width/2+10) + "," // TODO: change this 10
              + this.getBBox().height/2 + ")";
          });
      }

      var gSize = g[0][0].getBoundingClientRect();
      setHeight();

      function getXPos(d, i) {
        return margin.left + 80 + (d.starting_time - beginning) * scaleFactor;
      }

      function setHeight() {

        height = 3000;

        if (!height && !gParentItem.attr("height")) {
          if (itemHeight) {
            // set height based off of item height
            height = gSize.height + gSize.top - gParentSize.top;
            // set bounding rectangle height
            d3.select(gParent[0][0]).attr("height", height);
          } else {
            throw "height of the timeline is not set";
          }
        } else {
          if (!height) {
            height = gParentItem.attr("height");
          } else {
            gParentItem.attr("height", height);
          }
        }
      }

      function setWidth() {

        if (!width && !gParentSize.width) {
          throw "width of the timeline is not set";
        } else if (!(width && gParentSize.width)) {
          if (!width) {
            width = gParentItem.attr("width");
          } else {
            gParentItem.attr("width", width);
          }
        }
        // if both are set, do nothing
      }
    }

    timeline.margin = function (p) {
      if (!arguments.length) return margin;
      margin = p;
      return timeline;
    }

    timeline.orient = function (orientation) {
      if (!arguments.length) return orient;
      orient = orientation;
      return timeline;
    };

    timeline.itemHeight = function (h) {
      if (!arguments.length) return itemHeight;
      itemHeight = h;
      return timeline;
    }

    timeline.itemMargin = function (h) {
      if (!arguments.length) return itemMargin;
      itemMargin = h;
      return timeline;
    }

    timeline.height = function (h) {
      if (!arguments.length) return height;
      height = h;
      return timeline;
    };

    timeline.width = function (w) {
      if (!arguments.length) return width;
      width = w;
      return timeline;
    };

    timeline.display = function (displayType) {
      if (!arguments.length || (DISPLAY_TYPES.indexOf(displayType) == -1)) return display;
      display = displayType;
      return timeline;
    };

    timeline.tickFormat = function (format) {
      if (!arguments.length) return tickFormat;
      tickFormat = format;
      return timeline;
    };

    timeline.hover = function (hoverFunc) {
      if (!arguments.length) return hover;
      hover = hoverFunc;
      return timeline;
    };

    timeline.mouseover = function (mouseoverFunc) {
      if (!arguments.length) return mouseoverFunc;
      mouseover = mouseoverFunc;
      return timeline;
    };

    timeline.mouseout = function (mouseoverFunc) {
      if (!arguments.length) return mouseoverFunc;
      mouseout = mouseoverFunc;
      return timeline;
    };

    timeline.click = function (clickFunc) {
      if (!arguments.length) return click;
      click = clickFunc;
      return timeline;
    };

    timeline.scroll = function (scrollFunc) {
      if (!arguments.length) return scroll;
      scroll = scrollFunc;
      return timeline;
    }

    timeline.colors = function (colorFormat) {
      if (!arguments.length) return colorCycle;
      colorCycle = colorFormat;
      return timeline;
    };

    timeline.beginning = function (b) {
      if (!arguments.length) return beginning;
      beginning = b;
      return timeline;
    };

    timeline.ending = function (e) {
      if (!arguments.length) return ending;
      ending = e;
      return timeline;
    };

    timeline.rotateTicks = function (degrees) {
      rotateTicks = degrees;
      return timeline;
    }

    timeline.stack = function () {
      stacked = !stacked;
      return timeline;
    };

    return timeline;
  };
})();
          

