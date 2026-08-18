package cn.iocoder.yudao.framework.common.util.json.databind;

import cn.hutool.core.util.NumberUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.util.date.LocalDateTimeUtils;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;

import java.io.IOException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

/**
 * 基于时间戳的 LocalDateTime 反序列化器
 *
 * @author 老五
 */
public class TimestampLocalDateTimeDeserializer extends JsonDeserializer<LocalDateTime> {

    public static final TimestampLocalDateTimeDeserializer INSTANCE = new TimestampLocalDateTimeDeserializer();
    private static final DateTimeFormatter DEFAULT_FORMATTER =
            DateTimeFormatter.ofPattern(FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND);

    @Override
    public LocalDateTime deserialize(JsonParser p, DeserializationContext ctxt) throws IOException {
        JsonToken token = p.currentToken();
        if (token == JsonToken.VALUE_NULL) {
            return null;
        }

        if (token == JsonToken.VALUE_NUMBER_INT) {
            return LocalDateTime.ofInstant(Instant.ofEpochMilli(p.getLongValue()), ZoneId.systemDefault());
        }

        String text = p.getValueAsString();
        if (StrUtil.isBlank(text)) {
            return null;
        }
        if (NumberUtil.isLong(text)) {
            return LocalDateTime.ofInstant(Instant.ofEpochMilli(Long.parseLong(text)), ZoneId.systemDefault());
        }
        if (text.length() == FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND.length()) {
            return LocalDateTime.parse(text, DEFAULT_FORMATTER);
        }
        return LocalDateTimeUtils.parse(text);
    }

}
