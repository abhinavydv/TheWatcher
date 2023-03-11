function calculateDaysBetweenDates(begin, end) {
    var beginDate = new Date(begin);
    var endDate = new Date(end);
    var days = (endDate - beginDate) / 1000 / 60 / 60 / 24;
    return days;
}