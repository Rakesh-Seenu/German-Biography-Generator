var socket = io.connect('http://' + document.domain + ':' + location.port);

socket.on('update', function(data) {
    console.log("Received update:", data);  // For debugging
    var item = document.getElementById(data.file);
    if (item) {
        item.querySelector('span').textContent = data.status;
        if (data.status === 'Completed') {
            item.querySelector('span').className = 'badge badge-status bg-success';

            // Add download link when processing is completed
            var downloadLink = document.createElement('a');
            downloadLink.href = '/download/' + data.file.replace('.csv', '.pdf'); // Adjust if file extension changes
            downloadLink.textContent = 'Download PDF';
            downloadLink.className = 'btn btn-link ms-3'; // Optional styling
            item.appendChild(downloadLink);
        } else if (data.status === 'Failed') {
            item.querySelector('span').className = 'badge badge-status bg-danger';
        } else if (data.status === 'Processing') {
            item.querySelector('span').className = 'badge badge-status bg-primary';
        }
    } else {
        var newItem = document.createElement('li');
        newItem.id = data.file;
        newItem.className = 'list-group-item d-flex justify-content-between align-items-center';
        newItem.innerHTML = data.file + '<span class="badge badge-status bg-warning">' + data.status + '</span>';
        document.getElementById('status-list').appendChild(newItem);
    }
});
