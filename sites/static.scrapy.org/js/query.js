
(function($){
  
  window.initializeFilters = function() {
  
    // Bail early for Konqueror and IE5.2/Mac, which don't fully support dynamic
    // creation of form controls
    try {
      var test = document.createElement("input");
      test.type = "button";
      if (test.type != "button") throw Error();
    } catch (e) {
      return;
    }
  
    // Removes an existing row from the filters table
    function removeRow(button, propertyName) {
      var tr = getAncestorByTagName(button, "tr");
  
      var mode = null;
      var selects = tr.getElementsByTagName("select");
      for (var i = 0; i < selects.length; i++) {
        if (selects[i].name == propertyName + "_mode") {
          mode = selects[i];
          break;
        }
      }
      if (mode && (getAncestorByTagName(mode, "tr") == tr)) {
        // Check whether there are more 'or' rows for this filter
        var next = tr.nextSibling;
        if (next && (next.className == propertyName)) {
          function getChildElementAt(e, idx) {
            e = e.firstChild;
            var cur = 0;
            while (cur <= idx) {
              while (e && e.nodeType != 1) e = e.nextSibling;
              if (cur++ == idx) break;
              e = e.nextSibling;
            }
            return e;
          }
  
          var thisTh = getChildElementAt(tr, 0);
          var nextTh = getChildElementAt(next, 0);
          next.insertBefore(thisTh, nextTh);
          nextTh.colSpan = 1;
  
          thisTd = getChildElementAt(tr, 0);
          nextTd = getChildElementAt(next, 1);
          next.replaceChild(thisTd, nextTd);
        }
      }
  
      var tBody = tr.parentNode;
      tBody.deleteRow(tr.sectionRowIndex);
      if (!tBody.rows.length) {
          tBody.parentNode.removeChild(tBody);
      }
      
      if (propertyName) {
        var select = document.forms["query"].elements["add_filter"];
        for (var i = 0; i < select.options.length; i++) {
          var option = select.options[i];
          if (option.value == propertyName) option.disabled = false;
        }
      }
    }
  
    // Initializes a filter row, the 'input' parameter is the submit
    // button for removing the filter
    function initializeFilter(input) {
      var removeButton = document.createElement("input");
      removeButton.type = "button";
      removeButton.value = input.value;
      if (input.name.substr(0, 10) == "rm_filter_") {
        removeButton.onclick = function() {
          var endIndex = input.name.search(/_\d+$/);
          if (endIndex < 0) endIndex = input.name.length;
          removeRow(removeButton, input.name.substring(10, endIndex));
          return false;
        }
      } else {
        removeButton.onclick = function() {
          removeRow(removeButton);
          return false;
        }
      }
      input.parentNode.replaceChild(removeButton, input);
    }
  
    // Make the submit buttons for removing filters client-side triggers
    var filters = document.getElementById("filters");
    var inputs = filters.getElementsByTagName("input");
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      if (input.type == "submit" && input.name
       && input.name.match(/^rm_filter_/)) {
        initializeFilter(input);
      }
    }
  
    // Make the drop-down menu for adding a filter a client-side trigger
    var addButton = document.forms["query"].elements["add"];
    addButton.parentNode.removeChild(addButton);
    var select = document.getElementById("add_filter");
    select.onchange = function() {
      if (select.selectedIndex < 1) return;
  
      if (select.options[select.selectedIndex].disabled) {
        // Neither IE nor Safari supported disabled options at the time this was
        // written, so alert the user
        alert("A filter already exists for that property");
        return;
      }
  
      // Convenience function for creating a <label>
      function createLabel(text, htmlFor) {
        var label = document.createElement("label");
        if (text) label.appendChild(document.createTextNode(text));
        if (htmlFor) label.htmlFor = htmlFor;
        return label;
      }
  
      // Convenience function for creating an <input type="checkbox">
      function createCheckbox(name, value, id) {
        var input = document.createElement("input");
        input.type = "checkbox";
        if (name) input.name = name;
        if (value) input.value = value;
        if (id) input.id = id;
        return input;
      }
  
      // Convenience function for creating an <input type="radio">
      function createRadio(name, value, id) {
        var str = '<input type="radio"';
        if (name) str += ' name="' + name + '"';
        if (value) str += ' value="' + value + '"';
        if (id) str += ' id="' + id + '"'; 
        str += '/>';
        var span = document.createElement('span');
        // create radio button with innerHTML to avoid IE mangling it.
        span.innerHTML = str; 
        return span;
      }
  
      // Convenience function for creating a <select>
      function createSelect(name, options, optional) {
        var e = document.createElement("select");
        if (name) e.name = name;
        if (optional) e.options[0] = new Option();
        if (options) {
          for (var i = 0; i < options.length; i++) {
            var option;
            if (typeof(options[i]) == "object") {
              option = new Option(options[i].text, options[i].value);
            } else {
              option = new Option(options[i], options[i]);
            }
            e.options[e.options.length] = option;
          }
        }
        return e;
      }
  
      var propertyName = select.options[select.selectedIndex].value;
      var property = properties[propertyName];
      var table = document.getElementById("filters").getElementsByTagName("table")[0];
      var tr = document.createElement("tr");
      tr.className = propertyName;
  
      var alreadyPresent = false;
      for (var i = 0; i < table.rows.length; i++) {
        if (table.rows[i].className == propertyName) {
          var existingTBody = table.rows[i].parentNode;
          alreadyPresent = true;
          break;
        }
      }
  
      // Add the row header
      var th = document.createElement("th");
      th.scope = "row";
      if (!alreadyPresent) {
        th.appendChild(createLabel(property.label));
      } else {
        th.colSpan = 2;
        th.appendChild(createLabel("or"));
      }
      tr.appendChild(th);
  
      var td = document.createElement("td");
      if (property.type == "radio" || property.type == "checkbox") {
        td.colSpan = 2;
        td.className = "filter";
        if (property.type == "radio") {
          for (var i = 0; i < property.options.length; i++) {
            var option = property.options[i];
            td.appendChild(createCheckbox(propertyName, option,
              propertyName + "_" + option));
            td.appendChild(createLabel(option ? option : "none",
              propertyName + "_" + option));
          }
        } else {
          td.appendChild(createRadio(propertyName, "1", propertyName + "_on"));
          td.appendChild(document.createTextNode(" "));
          td.appendChild(createLabel("yes", propertyName + "_on"));
          td.appendChild(createRadio(propertyName, "0", propertyName + "_off"));
          td.appendChild(document.createTextNode(" "));
          td.appendChild(createLabel("no", propertyName + "_off"));
        }
        tr.appendChild(td);
      } else {
        if (!alreadyPresent) {
          // Add the mode selector
          td.className = "mode";
          var modeSelect = createSelect(propertyName + "_mode",
                                        modes[property.type]);
          td.appendChild(modeSelect);
          tr.appendChild(td);
        }
  
        // Add the selector or text input for the actual filter value
        td = document.createElement("td");
        td.className = "filter";
        if (property.type == "select") {
          var element = createSelect(propertyName, property.options, true);
        } else if (property.type == "text") {
          var element = document.createElement("input");
          element.type = "text";
          element.name = propertyName;
          element.size = 42;
        }
        td.appendChild(element);
        element.focus();
        tr.appendChild(td);
      }
  
      // Add the add and remove buttons
      td = document.createElement("td");
      td.className = "actions";
      var removeButton = document.createElement("input");
      removeButton.type = "button";
      removeButton.value = "-";
      removeButton.onclick = function() { removeRow(removeButton, propertyName) };
      td.appendChild(removeButton);
      tr.appendChild(td);
  
      if (alreadyPresent) {
        existingTBody.appendChild(tr);
      } else {
        // Find the insertion point for the new row. We try to keep the filter rows
        // in the same order as the options in the 'Add filter' drop-down, because
        // that's the order they'll appear in when submitted.
        var insertionPoint = getAncestorByTagName(select, "tbody");
        outer: for (var i = select.selectedIndex + 1; i < select.options.length; i++) {
          for (var j = 0; j < table.tBodies.length; j++) {
            if (table.tBodies[j].rows[0].className == select.options[i].value) {
              insertionPoint = table.tBodies[j];
              break outer;
            }
          }
        }
        // Finally add the new row to the table
        var tbody = document.createElement("tbody");
        tbody.appendChild(tr);
        insertionPoint.parentNode.insertBefore(tbody, insertionPoint);
      }
  
      // Disable the add filter in the drop-down list
      if (property.type == "radio" || property.type == "checkbox") {
        select.options[select.selectedIndex].disabled = true;
      }
      select.selectedIndex = 0;
    }
  }

})(jQuery);