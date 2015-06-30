
/* do not use following approach, this cannot work correctly!
function walk_dom(node, filter) {
	if (node === null) {
		return
	}
	
	var child = node.firstElementChild

	while (child) {
		child = filter(child, node)
		walk_dom(child, filter)//dom
		child = child.nextElementSibling

	}
}

walk_dom(document, function(child, node) {
	
	if (child.nodeName === "SCRIPT" || child.nodeName === "STYLE") {
		console.log(child)
		var next = child.nextElementSibling
		node.removeChild(child)// recommended to use 'hide'
		return next
	}
	return child
})

console.log(document)
*/


function walk_dom(node, _IsExec){
    if (node === null){
        return
    }
     
    var queue = [node], _curr = undefined
     
    while(queue.length){
        _curr = queue.shift()
        var _array = dom_Array(_curr.children)
		queue.extend(_IsExec(_curr, _array))
    }
	
	return node
}

// helper libs
function dom_Array(elements){
	var _array = []
	Array.prototype.push.apply(_array, elements)
	return _array
}

function extend(_array){
	Array.prototype.push.apply(this, _array)
	return this
}
Array.prototype.extend = extend


var node = walk_dom(document, function(parent, children) {
     
    var selected = []
     
    for (child of children) {
        if (child.nodeName === "SCRIPT" || child.nodeName === "STYLE") {
            parent.removeChild(child)
        }
		else {
			selected.push(child)
		}
    }
     
   return selected
})
// for interprocess communication 
console.log(node)

bodyText = node.body.innerText, 
body = node.body.innerHTML

bodyText = bodyText.split('\n').filter(function(node){
	if (node === "" ){return 0} return 1})  

return "success"