// Click a tag (e.g. #security) to search the DataTable for that tag.
$(document).ready(function () {
    $(document).on("click", ".tag-div, .chip > a[href='#']", function (e) {
        e.preventDefault();
        var tag = $(this).clone().children().remove().end().text().trim();
        var table = $(this).closest("table.dataTable");
        if (!table.length) {
            // Clicked from outside the table (e.g. the dropdown key).
            table = $("table.dataTable");
        }
        if (table.length) {
            var dt = table.DataTable();
            dt.search(tag).draw();
            // Also update the visible search input
            var wrapper = $(table).closest(".dataTables_wrapper");
            wrapper.find("input[type='search']").val(tag);
        }
    });
});
