$(function(){

  function evalXPath($xpath, $html_input) {
    var $node = $($.parseXML($html_input.val()));
    var xpathExpr = $xpath.val();
    console.log('expr', xpathExpr);
    return $node.xpath(xpathExpr);
  }

  function nodeToString(node) {
    if (node.nodeType == 2)
      return node.value;
    if (node.nodeType == 3)
      return node.wholeText;
    if (node.nodeType == 8)
      return "<!--" + node.textContent + "-->";
    if (node.outerHTML === undefined)
      return node;
    return node.outerHTML;
  }

  function evalXPathUpdateResult() {
    var $xpath = $(this);
    var target_id = $xpath.data('target');
    var $html_input = $('#html_input-' + target_id);
    var $html_output = $('#html_output-' + target_id);

    try {
      var nodes = evalXPath($xpath, $html_input);
      var htmlNodes = $.map(nodes, function(node){
        return $("<div>").text(nodeToString(node)).addClass("result_node");
      });

      $html_output.removeClass('error_output');
      $html_output.html(htmlNodes)
      console.info('nodes', nodes);
    } catch (e) {
      // don't show the "expected expression" message when empty
      if (e.code === "XPST0003" && $xpath.val() === '') {
        $html_output.html('');
      } else {
        $html_output.addClass('error_output');
        // TODO: show nicer error message
        $html_output.html("ERROR: " + e.message);
      }
      console.error(e);
    }
  }

  $('.xpath_expression').on('keyup', evalXPathUpdateResult);
  $('.xpath_expression').each(evalXPathUpdateResult);
})
