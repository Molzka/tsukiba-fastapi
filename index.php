<?php
date_default_timezone_set('Europe/Moscow');

function dbExist() {
    return is_file('assets/database.db');
}

function connectDB() {
    static $pdo;
    if (!$pdo) $pdo = new PDO('sqlite:assets/database.db');
    return $pdo;
}

function createTables($db) {
    $db->exec('CREATE TABLE IF NOT EXISTS options (max_file_size INTEGER, bump_limit INTEGER, max_threads INTEGER, max_message_length INTEGER, captcha TEXT, id INTEGER PRIMARY KEY, stop_board BOOLEAN, password TEXT); CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, parent INTEGER, sage BOOLEAN, time TEXT, message TEXT, file1 TEXT, file1_info TEXT, file2 TEXT, file2_info TEXT, file3 TEXT, file3_info TEXT, file4 TEXT, file4_info TEXT, status INTEGER, status_time INTEGER, password TEXT, verify TEXT); CREATE INDEX IF NOT EXISTS idx_parent ON posts(parent); CREATE INDEX IF NOT EXISTS idx_status ON posts(status); CREATE INDEX IF NOT EXISTS idx_parent_status ON posts(parent, status)');
}

function saveOptions($db, $options) {
    $stmt = $db->prepare('INSERT INTO options (max_file_size, bump_limit, max_threads, max_message_length, captcha, id, stop_board, password) VALUES (:max_file_size, :bump_limit, :max_threads, :max_message_length, :captcha, :id, :stop_board, :password)');
    $stmt->execute($options);
}

function updateOptions($db, $options) {
    $stmt = $db->prepare('UPDATE options SET max_file_size = :max_file_size, bump_limit = :bump_limit, max_threads = :max_threads, max_message_length = :max_message_length, captcha = :captcha, stop_board = :stop_board, password = :password WHERE id = :id');
    $stmt->execute($options);
}

function postExists($id) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT 1 FROM posts WHERE id = :id LIMIT 1");
    $stmt->execute(['id' => $id]);
    return (bool)$stmt->fetchColumn();
}

function getReplies($postId, $threadId) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT * FROM posts WHERE parent = :threadId AND (status = 0 OR status = 3) AND (message LIKE '%<post-link>&gt;&gt;' || :postId || '</post-link>%') ORDER BY id ASC");
    $stmt->execute(['threadId' => $threadId, 'postId' => $postId]);
    return $stmt->fetchAll(PDO::FETCH_ASSOC);
}

function getFromDB($table, $value) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT {$value} FROM {$table} ORDER BY id DESC LIMIT 1");
    $stmt->execute();
    return $stmt->fetchColumn();
}

function truncateString($string, $length) {
    if (mb_strlen($string, 'UTF-8') <= $length) return $string;
    $truncated = mb_substr($string, 0, $length, 'UTF-8');
    $lastSpace = mb_strrpos($truncated, ' ', 0, 'UTF-8');
    if ($lastSpace !== false) $truncated = mb_substr($truncated, 0, $lastSpace, 'UTF-8');
    else {
        $entityEnd = mb_strpos($string, ';', $length, 'UTF-8');
        if ($entityEnd !== false && $entityEnd - $length <= 8) $truncated = mb_substr($string, 0, $entityEnd + 1, 'UTF-8');
    }
    return $truncated . '...';
}

function readableBytes($bytes) {
    if ($bytes === 0) return '0Б';
    $sizes = ['Б', 'Кб', 'Мб', 'Гб'];
    $i = min(3, (int)floor(log($bytes, 1024)));
    return sprintf('%.02F', $bytes / pow(1024, $i)) * 1 . $sizes[$i];
}

function getThreads($limit = null, $offset = 0) {
    $db = connectDB();
    $sql = "SELECT t.*, MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) as last_bump FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 0 WHERE t.parent = 0 AND t.status = 0 GROUP BY t.id ORDER BY last_bump DESC";
    if ($limit !== null && $limit > 0) {
        $sql .= " LIMIT :limit OFFSET :offset";
        $stmt = $db->prepare($sql);
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    } else $stmt = $db->prepare($sql);
    $stmt->execute();
    return $stmt->fetchAll(PDO::FETCH_ASSOC);
}

function searchInThread($threadId, $searchText) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT message FROM posts WHERE id = :id AND parent = 0 AND status = 0");
    $stmt->execute(['id' => $threadId]);
    $message = $stmt->fetchColumn();
    if (!is_string($message)) return false;
    return mb_strpos(mb_strtolower($message, 'UTF-8'), mb_strtolower($searchText, 'UTF-8')) !== false;
}

function sanitizePost($post) {
    unset($post['parent'], $post['status'], $post['status_time'], $post['password'], $post['verify'], $post['last_bump']);
    return $post;
}

function countReplies($threadId) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE parent = :threadId AND (status = 0 OR status = 3)");
    $stmt->execute(['threadId' => $threadId]);
    return $stmt->fetchColumn();
}

function getActiveThreadsList() {
    $threads = getThreads();
    return array_map(function($thread) {
        $sanitized = sanitizePost($thread);
        $sanitized['replies'] = countReplies($thread['id']);
        $sanitized['opmod'] = !empty($thread['password']) ? 1 : null;
        return $sanitized;
    }, $threads);
}

function getThreadContents($threadId) {
    $db = connectDB();
    $stmt = $db->prepare("WITH RECURSIVE thread_posts AS (SELECT * FROM posts WHERE id = :id UNION ALL SELECT p.* FROM posts p INNER JOIN thread_posts tp ON p.parent = tp.id WHERE p.status = 0) SELECT * FROM thread_posts ORDER BY id ASC");
    $stmt->execute(['id' => $threadId]);
    return array_map('sanitizePost', $stmt->fetchAll(PDO::FETCH_ASSOC));
}

function getPostInfo($postId) {
    $db = connectDB();
    $stmt = $db->prepare("SELECT * FROM posts WHERE id = :id AND status = 0");
    $stmt->execute(['id' => $postId]);
    $post = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$post) return null;
    $sanitized = sanitizePost($post);
    $sanitized['parent'] = $post['parent'];
    return $sanitized;
}

function captchaImage($captchaCode) {
    $captchaType = getFromDB('options', 'captcha');
    $width = 69; $height = 20;
    $image = imagecreatetruecolor($width, $height);
    $fontFile = 'assets/font.ttf';
    $fontSize = 14;
    $charWidth = $fontSize + 2;
    $background = imagecolorallocate($image, 221, 221, 221);
    $text = imagecolorallocate($image, 51, 51, 51);
    imagefill($image, 0, 0, $background);
    switch ($captchaType) {
        case 'simple':
            for ($i = 0, $len = mb_strlen($captchaCode); $i < $len; $i++) {
                $char = mb_substr($captchaCode, $i, 1);
                $x = 5 + ($i * $charWidth);
                $y = rand(14, 18);
                $randomSpin = rand(-10, 10);
                imagettftext($image, $fontSize, $randomSpin, $x, $y, $text, $fontFile, $char);
            }
            break;
        case 'shadow':
            for ($i = 0, $len = mb_strlen($captchaCode); $i < $len; $i++) {
                $char = mb_substr($captchaCode, $i, 1);
                $x = 5 + ($i * $charWidth);
                $y = rand(14, 18);
                $randomSpin = rand(-10, 10);
                $oneOrTwo = rand(0, 1) === 0 ? -1 : 1;
                imagettftext($image, $fontSize, $randomSpin, $x + $oneOrTwo, $y + $oneOrTwo, $text, $fontFile, $char);
                imagettftext($image, $fontSize, $randomSpin, $x, $y, $background, $fontFile, $char);
            }
            for ($i = 0; $i < 100; $i++) imagesetpixel($image, rand(0, 89), rand(0, 20), $background);
            break;
    }
    ob_start();
    imagewebp($image, null, 50);
    $imageData = ob_get_contents();
    ob_end_clean();
    return 'data:image/webp;base64,' . base64_encode($imageData);
}

function generateCaptchaCode() {
    $letters = mb_str_split('абвгдежзиклмнопрстуфхцчшщыьэюя');
    $code = '';
    for ($i = 0, $len = rand(3, 4); $i < $len; $i++) $code .= $letters[array_rand($letters)];
    return $code;
}

function generateApiCaptcha() {
    $captchaCode = generateCaptchaCode();
    $captchaVerify = hash_hmac('sha256', $captchaCode, getFromDB('options', 'password') . date('YmdH'));
    return ['captcha_image' => captchaImage($captchaCode), 'verify' => $captchaVerify];
}

function getImageDimensions($file) {
    $imageSize = getimagesize($file);
    return $imageSize[0] . 'x' . $imageSize[1];
}

function getVideoInfo($file) {
    $resolution = trim(shell_exec("ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 {$file}")) ?: '?';
    $duration = shell_exec("ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 {$file}");
    $duration = is_numeric(trim($duration)) ? gmdate("H:i:s", (int)$duration) : '?';
    return [$resolution, $duration];
}

function createThumbnail($source, $destination, $maxSize) {
    [$width, $height] = getimagesize($source);
    $aspectRatio = $width / $height;
    if ($width <= $maxSize && $height <= $maxSize) {
        $thumbWidth = $width; $thumbHeight = $height;
    } elseif ($width > $height) {
        $thumbWidth = $maxSize; $thumbHeight = (int)($maxSize / $aspectRatio);
    } else {
        $thumbHeight = $maxSize; $thumbWidth = (int)($maxSize * $aspectRatio);
    }
    $thumb = imagecreatetruecolor($thumbWidth, $thumbHeight);
    $sourceImage = imagecreatefromstring(file_get_contents($source));
    $backgroundColor = imagecolorallocate($thumb, 234, 234, 234);
    imagefill($thumb, 0, 0, $backgroundColor);
    imagecopyresampled($thumb, $sourceImage, 0, 0, 0, 0, $thumbWidth, $thumbHeight, $width, $height);
    imagewebp($thumb, $destination, 50);
}

function createVideoThumbnail($source, $destination, $maxSize) {
    $duration = (int)shell_exec("ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 {$source}");
    $randomTime = sprintf('%.3f', rand(0, min(5, $duration)));
    $videoInfo = shell_exec("ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 {$source}");
    list($width, $height) = explode('x', $videoInfo);
    $aspectRatio = $width / $height;
    if ($width <= $maxSize && $height <= $maxSize) {
        $thumbWidth = $width; $thumbHeight = $height;
    } elseif ($width > $height) {
        $thumbWidth = $maxSize; $thumbHeight = (int)($maxSize / $aspectRatio);
    } else {
        $thumbHeight = $maxSize; $thumbWidth = (int)($maxSize * $aspectRatio);
    }
    shell_exec("ffmpeg -ss {$randomTime} -i {$source} -vf \"scale={$thumbWidth}:{$thumbHeight}:force_original_aspect_ratio=decrease\" -vframes 1 -f image2 -q:v 50 {$destination}");
}

function getSubdirPath($hash) {
    return substr($hash, 0, 2);
}

function uploadFiles($files) {
    $uploadedFiles = [];
    foreach ($files['name'] as $key => $name) {
        if ($files['error'][$key] === UPLOAD_ERR_OK) {
            $tmpName = $files['tmp_name'][$key];
            $fileContents = file_get_contents($tmpName);
            $fileHash = hash('xxh3', $fileContents);
            $extension = strtolower(pathinfo($name, PATHINFO_EXTENSION));
            if ($extension === 'jpeg') $extension = 'jpg';
            $fileName = $fileHash . '.' . $extension;
            $subdir = getSubdirPath($fileHash);
            $mediaDir = 'media/' . $subdir;
            $thumbDir = 'thumb/' . $subdir;
            if (!is_dir($mediaDir)) mkdir($mediaDir, 0777, true);
            if (!is_dir($thumbDir)) mkdir($thumbDir, 0777, true);
            $filePath = $mediaDir . '/' . $fileName;
            $thumbPath = $thumbDir . '/' . $fileHash . '.webp';
            if (!file_exists($filePath)) {
                if (move_uploaded_file($tmpName, $filePath)) {
                    shell_exec("exiftool -all= -overwrite_original {$filePath}");
                    $fileInfo = readableBytes(filesize($filePath));
                    if (strpos($files['type'][$key], 'image') !== false) {
                        $fileInfo .= ', ' . getImageDimensions($filePath);
                        createThumbnail($filePath, $thumbPath, 180);
                    } elseif (strpos($files['type'][$key], 'video') !== false) {
                        [$resolution, $duration] = getVideoInfo($filePath);
                        $fileInfo .= ', ' . $resolution . ', ' . $duration;
                        createVideoThumbnail($filePath, $thumbPath, 180);
                    }
                    $uploadedFiles[] = ['name' => $fileName, 'info' => $fileInfo];
                }
            } else {
                $fileInfo = readableBytes(filesize($filePath));
                if (strpos($files['type'][$key], 'image') !== false) $fileInfo .= ', ' . getImageDimensions($filePath);
                elseif (strpos($files['type'][$key], 'video') !== false) {
                    [$resolution, $duration] = getVideoInfo($filePath);
                    $fileInfo .= ', ' . $resolution . ', ' . $duration;
                }
                $uploadedFiles[] = ['name' => $fileName, 'info' => $fileInfo];
            }
        }
    }
    return $uploadedFiles;
}

function transformMessage($message) {
    $message = htmlspecialchars($message, ENT_QUOTES, 'UTF-8');
    $message = preg_replace('/\p{M}+/u', '', $message);
    $message = preg_replace('/[ \t]+/', ' ', $message);
    $message = preg_replace_callback('/&gt;&gt;(\d+)/', function($matches) {
        static $count = 0;
        if ($count >= 20) return $matches[0];
        if (postExists($matches[1])) {
            $count++;
            return "<post-link>&gt;&gt;{$matches[1]}</post-link>";
        }
        return $matches[0];
    }, $message, 20);
    $message = preg_replace_callback('/^&gt;(.*)$/m', fn($m) => '<span class="quote">&gt;' . rtrim($m[1]) . '</span>', $message);
    $message = trim($message);
    $tags = ['sp' => ['span', ' class="spoiler"'], 's' => ['s', ''], 'i' => ['i', '']];
    while (preg_match('/\[(sp|s|i)\]((?:[^[]|\[(?!\/?\1\])|(?R))*)\[\/\1\]/is', $message, $matches)) {
        $tag = $tags[$matches[1]][0];
        $attr = $tags[$matches[1]][1];
        $content = $matches[2];
        $message = str_replace($matches[0], "<{$tag}{$attr}>{$content}</{$tag}>", $message);
    }
    $message = str_replace(["\r\n", "\r", "\n"], '<br>', $message);
    $message = preg_replace_callback('~https?://[\w.-]+[\w](?:/(?:\([^<>\s]+\)|[^()<>\s]*[^()<>\s.,?:;\n])*)?~', function($matches) {
        $url = $matches[0];
        $decodedUrl = htmlspecialchars(urldecode(htmlspecialchars_decode($url, ENT_QUOTES)), ENT_QUOTES, 'UTF-8');
        return "<a href=\"{$url}\" target=\"_blank\" rel=\"noreferrer nofollow\">{$decodedUrl}</a>";
    }, $message);
    return $message;
}

function validateMessage($message) {
    if (mb_strlen($message) > getFromDB('options', 'max_message_length')) return 1;
    if (substr_count($message, "\n") > 100) return 2;
    if (mb_strlen($message) >= 1000) {
        $words = preg_split('/\s+/', mb_strtolower($message));
        $wordCount = array_count_values($words);
        foreach ($wordCount as $word => $count) {
            if (mb_strlen($word) <= 2 || is_numeric($word)) continue;
            if ($count >= 100) return 2;
        }
    }
    $normalizedMessage = mb_substr(transformMessage($message), 0, 100);
    $db = connectDB();
    $stmt = $db->prepare("SELECT SUBSTR(message, 1, 100) as message FROM posts WHERE status = 1 AND LENGTH(message) > 8 ORDER BY id DESC LIMIT 500");
    $stmt->execute();
    foreach ($stmt->fetchAll(PDO::FETCH_COLUMN) as $deletedPost) {
        similar_text($normalizedMessage, $deletedPost, $percent);
        if ($percent > 90) return 2;
    }
    return 0;
}

function validateFiles($files) {
    if (empty($files['name'][0])) return 1;
    if (count($files['name']) > 4) return 2;
    $allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'video/mp4', 'video/webm'];
    $allowedExtensions = ['jpg', 'jpeg', 'png', 'gif', 'mp4', 'webm'];
    $maxFileSize = getFromDB('options', 'max_file_size');
    $finfo = new finfo(FILEINFO_MIME_TYPE);
    $fileHashes = [];
    foreach ($files['tmp_name'] as $tmpName) $fileHashes[] = hash('xxh3', file_get_contents($tmpName));
    $db = connectDB();
    $stmt = $db->prepare("SELECT file1, file2, file3, file4 FROM posts WHERE status = 1 ORDER BY id DESC LIMIT 500");
    $stmt->execute();
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $deletedPost) {
        foreach ($deletedPost as $file) {
            if (!empty($file)) {
                $fileHash = pathinfo($file, PATHINFO_FILENAME);
                if (in_array($fileHash, $fileHashes)) return 6;
            }
        }
    }
    foreach ($files['tmp_name'] as $key => $tmpName) {
        $mimeType = $finfo->file($tmpName);
        $extension = strtolower(pathinfo($files['name'][$key], PATHINFO_EXTENSION));
        if (!in_array($mimeType, $allowedTypes) || !in_array($extension, $allowedExtensions)) return 3;
        if (in_array($mimeType, ['image/jpeg', 'image/png', 'image/gif'])) {
            if (@getimagesize($tmpName) === false) return 4;
        } else {
            $videoInfo = shell_exec("ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 {$tmpName}");
            if (trim($videoInfo) !== 'video') return 4;
        }
    }
    if (array_sum($files['size']) > $maxFileSize) return 5;
    return 0;
}

function generatePostLinks($message) {
    return preg_replace_callback('/<post-link>&gt;&gt;(\d+)<\/post-link>/', function($matches) {
        $postId = $matches[1];
        $db = connectDB();
        $stmt = $db->prepare("SELECT parent, message, file1, file2, file3, file4, status FROM posts WHERE id = :id");
        $stmt->execute(['id' => $postId]);
        $post = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($post) {
            if ($post['status'] === 1 || $post['status'] === 2) return "<post-link class=\"deleted-reply\" title=\"Пост удалён\">&gt;&gt;{$postId}</post-link>";
            $linkClass = ($post['parent'] === 0) ? 'thread-reply' : 'post-reply';
            $fileCount = array_filter([$post['file1'], $post['file2'], $post['file3'], $post['file4']]);
            $fileInfo = count($fileCount) === 1 ? '(Файл)&#013;' : (count($fileCount) > 1 ? '(Файлы)&#013;' : '');
            $snippet = truncateString(strip_tags($fileInfo . str_replace('<br>', '&#013;', $post['message'] ?? '')), 500);
            $threadId = ($post['parent'] === 0) ? $postId : $post['parent'];
            $linkPrefix = ($post['status'] === 3) ? 'archived' : 'thread';
            return "<a class=\"{$linkClass}\" href=\"/{$linkPrefix}/{$threadId}#{$postId}\" title=\"{$snippet}\"><post-link>&gt;&gt;{$postId}</post-link></a>";
        }
        return $matches[0];
    }, $message ?? '');
}

function replaceShortPageLinks($content, $threadId, $shortThreadPosts) {
    return preg_replace_callback('/<a class="(thread-reply|post-reply)" href="\/thread\/(\d+)#(\d+)"([^>]*)><post-link>&gt;&gt;(\d+)<\/post-link><\/a>/', function($matches) use ($threadId, $shortThreadPosts) {
        if ((int)$matches[2] === (int)$threadId && in_array($matches[3], $shortThreadPosts)) return "<a class=\"{$matches[1]}\" href=\"/short/{$matches[2]}#{$matches[3]}\"{$matches[4]}><post-link>&gt;&gt;{$matches[5]}</post-link></a>";
        return $matches[0];
    }, $content);
}

function cleanupFiles() {
    $db = connectDB();
    $sevenDaysAgo = time() - (60 * 60 * 24 * 7);
    $stmt = $db->prepare("SELECT DISTINCT file1, file2, file3, file4 FROM posts WHERE status = 0 OR (status IN (1, 2, 3) AND status_time >= :sevenDaysAgo)");
    $stmt->execute(['sevenDaysAgo' => $sevenDaysAgo]);
    $protectedFiles = [];
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $fileSet) foreach ($fileSet as $file) if (!empty($file)) $protectedFiles[$file] = true;
    $stmt = $db->prepare("SELECT DISTINCT file1, file2, file3, file4 FROM posts WHERE status IN (1, 2, 3) AND status_time < :sevenDaysAgo");
    $stmt->execute(['sevenDaysAgo' => $sevenDaysAgo]);
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $fileSet) {
        foreach ($fileSet as $file) {
            if (empty($file)) continue;
            if (!isset($protectedFiles[$file])) {
                $fileHash = pathinfo($file, PATHINFO_FILENAME);
                $subdir = getSubdirPath($fileHash);
                $filePath = 'media/' . $subdir . '/' . $file;
                if (file_exists($filePath)) unlink($filePath);
            }
        }
    }
}

function generateFile($file, $fileInfo) {
    $ext = strtoupper(pathinfo($file, PATHINFO_EXTENSION));
    $videoThumb = in_array(pathinfo($file, PATHINFO_EXTENSION), ['mp4', 'webm']) ? ' video-thumb' : '';
    $fileHash = pathinfo($file, PATHINFO_FILENAME);
    $subdir = getSubdirPath($fileHash);
    $thumb = $fileHash . '.webp';
    $thumbPath = "thumb/{$subdir}/{$thumb}";
    $mediaPath = "media/{$subdir}/{$file}";
    list($thumbWidth, $thumbHeight) = file_exists($thumbPath) ? getimagesize($thumbPath) : [0, 0];
    $fileExists = file_exists($mediaPath);
    $fileLink = $fileExists ? "<a href=\"/media/{$subdir}/{$file}\" title=\"Скачать файл\" download>{$ext}</a>" : "<s title=\"Файл удалён\">{$ext}</s>";
    $imgLink = $fileExists ? "/media/{$subdir}/{$file}" : "/thumb/{$subdir}/{$thumb}";
    return "\n\t\t\t\t\t\t\t<div class=\"post-file\">\n\t\t\t\t\t\t\t\t<div class=\"file-info\">{$fileLink}, {$fileInfo}</div>\n\t\t\t\t\t\t\t\t<a href=\"{$imgLink}\" target=\"_blank\"><img class=\"file-thumb{$videoThumb}\" src=\"/thumb/{$subdir}/{$thumb}\" width=\"{$thumbWidth}\" height=\"{$thumbHeight}\"></a>\n\t\t\t\t\t\t\t</div>";
}

function generatePostForm($parent = 0, $pageType = 'normal') {
    $captchaCode = generateCaptchaCode();
    $captchaVerify = hash_hmac('sha256', $captchaCode, getFromDB('options', 'password') . date('YmdH'));
    $captcha = captchaImage($captchaCode);
    $maxLength = getFromDB('options', 'max_message_length');
    $pageTypeInput = $pageType === 'short' ? "\n\t\t\t<input type=\"hidden\" name=\"page-type\" value=\"short\">" : '';
    $passwordOrSage = $parent === 0 ? '<input class="op-mod-pass" type="password" name="password" maxlength="100" placeholder="Пароль от треда">' : '<label class="sage-label"><input type="checkbox" name="sage" value="1"> Не поднимать тред</label>';
    return "<form class=\"new-post-form\" id=\"postform\" method=\"post\" action=\"/post\" enctype=\"multipart/form-data\">{$pageTypeInput}\n\t\t\t<input type=\"hidden\" name=\"parent\" value=\"{$parent}\">\n\t\t\t<input type=\"hidden\" name=\"verify\" value=\"{$captchaVerify}\">\n\t\t\t<div class=\"post-form\">\n\t\t\t\t<a class=\"close-button\" href=\"##\">×</a>\n\t\t\t\t{$passwordOrSage}\n\t\t\t\t<input class=\"submit-new-post\" type=\"submit\" value=\"Отправить\">\n\t\t\t\t<textarea class=\"message-field\" name=\"message\" maxlength=\"{$maxLength}\" placeholder=\"Комментарий. Макс. длина: {$maxLength}.\"></textarea>\n\t\t\t\t<input class=\"captcha-field\" type=\"text\" name=\"captcha\" maxlength=\"4\" autocomplete=\"off\" placeholder=\"Капча\">\n\t\t\t\t<img class=\"captcha-image\" src=\"{$captcha}\">\n\t\t\t\t<input class=\"file-field\" type=\"file\" name=\"files[]\" multiple title=\"Разрешено прикреплять до 4 файлов\">\n\t\t\t</div>\n\t\t</form>";
}

function generateThread($thread, $isThreadPage = false, $status = 0) {
    $generateFiles = '';
    $fileCount = 0;
    for ($i = 1; $i <= 4; $i++) {
        $fileKey = "file$i";
        $fileInfoKey = "file{$i}_info";
        if (!empty($thread[$fileKey])) {
            $fileCount++;
            $generateFiles .= generateFile($thread[$fileKey], $thread[$fileInfoKey]);
        }
    }
    $postFileClass = $fileCount > 0 ? ($fileCount <= 1 ? ' post-with-file' : ' post-with-files') : '';
    $opModIndicator = $thread['password'] ? ' <span class="op-mod-indicator" title="ОП-модерация">(М)</span>' : '';
    $replyCount = countReplies($thread['id']);
    $linkOrReply = $status !== 0 ? ($status === 2 ? " | <a class=\"reply-link\" href=\"/short/{$thread['id']}#postform\" title=\"Ответить\">&gt;&gt;<span class=\"hidden\">{$thread['id']}</span></a>" : '') : ($isThreadPage ? " | <a class=\"reply-link\" href=\"/thread/{$thread['id']}#postform\" title=\"Ответить\">&gt;&gt;<span class=\"hidden\">{$thread['id']}</span></a>" : " | <a href=\"/thread/{$thread['id']}\">Открыть</a>");
    if ($replyCount >= 100 && $status === 0 && !$isThreadPage) $linkOrReply .= " | <a href=\"/short/{$thread['id']}\">Сокращённый</a>";
    $innerBox = "<a class=\"mod-link\" href=\"#mod\"><input id=\"mod-{$thread['id']}\" class=\"mod-box\" name=\"mod-box[]\" type=\"checkbox\" value=\"{$thread['id']}\"></a>";
    if ($status === 0) $innerLink = " class=\"header-link\" href=\"/thread/{$thread['id']}#{$thread['id']}\"";
    elseif ($status === 2) $innerLink = " class=\"header-link\" href=\"/short/{$thread['id']}#{$thread['id']}\"";
    elseif ($status === 3) {
        $innerBox = '';
        $innerLink = " class=\"header-link\" href=\"/archived/{$thread['id']}#{$thread['id']}\"";
    } else $innerLink = ' class="empty-link"';
    $message = generatePostLinks($thread['message']);
    $replies = getReplies($thread['id'], $thread['id']);
    $replyBlock = '';
    if (!empty($replies)) {
        $replyBlock = "\n\t\t\t\t\t\t\t<div class=\"backlinks\">Ответы:&nbsp;";
        $replyLinks = [];
        foreach ($replies as $reply) $replyLinks[] = "<post-link>&gt;&gt;{$reply['id']}</post-link>";
        $replyBlock .= generatePostLinks(implode(', ', $replyLinks));
        $replyBlock .= "</div>";
    }
    $showFiles = $generateFiles ? "\n\t\t\t\t\t\t\t<div class=\"files\">{$generateFiles}\n\t\t\t\t\t\t\t</div>" : '';
    return "\n\t\t\t\t\t<div id=\"{$thread['id']}\" class=\"thread-id\">\n\t\t\t\t\t\t<div id=\"post-{$thread['id']}\" class=\"thread post-height{$postFileClass}\" tabindex=\"0\">\n\t\t\t\t\t\t\t<div class=\"post-header\">{$innerBox}<a{$innerLink}><span class=\"post-number\">№{$thread['id']}</span><span class=\"post-time\"> {$thread['time']}</span></a>{$opModIndicator}{$linkOrReply}</div>{$showFiles}\n\t\t\t\t\t\t\t<div class=\"post-message\">{$message}</div>{$replyBlock}\n\t\t\t\t\t\t</div>\n\t\t\t\t\t</div>";
}

function generatePost($post, $isThreadPage = false, $status = 0) {
    $generateFiles = '';
    $fileCount = 0;
    for ($i = 1; $i <= 4; $i++) {
        $fileKey = "file$i";
        $fileInfoKey = "file{$i}_info";
        if (!empty($post[$fileKey])) {
            $fileCount++;
            $generateFiles .= generateFile($post[$fileKey], $post[$fileInfoKey]);
        }
    }
    $postFileClass = $fileCount > 0 ? ($fileCount <= 1 ? ' post-with-file' : ' post-with-files') : '';
    $sageIndicator = $post['sage'] ? ' <span class="sage-indicator">(Сажа)</span>' : '';
    $innerBox = "<a class=\"mod-link\" href=\"#mod\"><input id=\"mod-{$post['id']}\" class=\"mod-box\" name=\"mod-box[]\" type=\"checkbox\" value=\"{$post['id']}\"></a>";
    $innerReply = '';
    if ($status === 0) {
        $innerLink = " class=\"header-link\" href=\"/thread/{$post['parent']}#{$post['id']}\"";
        $innerReply = $isThreadPage ? " | <a class=\"reply-link\" href=\"/thread/{$post['parent']}#postform\" title=\"Ответить\">&gt;&gt;<span class=\"hidden\">{$post['id']}</span></a>" : '';
    } elseif ($status === 2) {
        $innerLink = " class=\"header-link\" href=\"/short/{$post['parent']}#{$post['id']}\"";
        $innerReply = " | <a class=\"reply-link\" href=\"/short/{$post['parent']}#postform\" title=\"Ответить\">&gt;&gt;<span class=\"hidden\">{$post['id']}</span></a>";
    } elseif ($status === 3) {
        $innerBox = '';
        $innerLink = " class=\"header-link\" href=\"/archived/{$post['parent']}#{$post['id']}\"";
    } else $innerLink = ' class="empty-link"';
    $message = generatePostLinks($post['message']);
    $replies = getReplies($post['id'], $post['parent']);
    $replyBlock = '';
    if (!empty($replies)) {
        $replyBlock = "\n\t\t\t\t\t\t\t<div class=\"backlinks\">Ответы:&nbsp;";
        $replyLinks = [];
        foreach ($replies as $reply) $replyLinks[] = "<post-link>&gt;&gt;{$reply['id']}</post-link>";
        $replyBlock .= generatePostLinks(implode(', ', $replyLinks));
        $replyBlock .= "</div>";
    }
    $showFiles = $generateFiles ? "\n\t\t\t\t\t\t\t<div class=\"files\">{$generateFiles}\n\t\t\t\t\t\t\t</div>" : '';
    return "\n\t\t\t\t\t<div id=\"{$post['id']}\" class=\"post-id\">\n\t\t\t\t\t\t<div id=\"post-{$post['id']}\" class=\"post post-height{$postFileClass}\" tabindex=\"0\">\n\t\t\t\t\t\t\t<div class=\"post-header\">{$innerBox}<a{$innerLink}><span class=\"post-number\">№{$post['id']}</span><span class=\"post-time\"> {$post['time']}</span></a>{$sageIndicator}{$innerReply}</div>{$showFiles}\n\t\t\t\t\t\t\t<div class=\"post-message\">{$message}</div>{$replyBlock}\n\t\t\t\t\t\t</div>\n\t\t\t\t\t</div>";
}

function manageThreadStatuses() {
    $db = connectDB();
    $maxThreads = getFromDB('options', 'max_threads');
    if ($maxThreads <= 0) return;
    $db->beginTransaction();
    $statusTime = (int)(substr(time(), 0, -3) . '000');
    $stmt = $db->prepare("UPDATE posts SET status = 3, status_time = :statusTime WHERE id IN (SELECT id FROM (SELECT t.id FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 0 WHERE t.parent = 0 AND t.status = 0 GROUP BY t.id ORDER BY MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) DESC LIMIT :offset, 9223372036854775807) AS threads_to_archive) OR parent IN (SELECT id FROM (SELECT t.id FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 0 WHERE t.parent = 0 AND t.status = 0 GROUP BY t.id ORDER BY MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) DESC LIMIT :offset, 9223372036854775807) AS threads_to_archive) AND status = 0");
    $stmt->bindValue(':offset', $maxThreads, PDO::PARAM_INT);
    $stmt->bindValue(':statusTime', $statusTime, PDO::PARAM_INT);
    $stmt->execute();
    $activeThreadCount = $db->query("SELECT COUNT(*) FROM posts WHERE parent = 0 AND status = 0")->fetchColumn();
    $limit = max(0, $maxThreads - $activeThreadCount);
    $stmt = $db->prepare("UPDATE posts SET status = 0, status_time = :statusTime WHERE id IN (SELECT id FROM (SELECT t.id FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 3 WHERE t.parent = 0 AND t.status = 3 GROUP BY t.id ORDER BY MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) DESC LIMIT :limit) AS threads_to_activate) OR parent IN (SELECT id FROM (SELECT t.id FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 3 WHERE t.parent = 0 AND t.status = 3 GROUP BY t.id ORDER BY MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) DESC LIMIT :limit) AS threads_to_activate) AND status = 3");
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':statusTime', $statusTime, PDO::PARAM_INT);
    $stmt->execute();
    $db->commit();
}

function handlePostSubmission($parent = 0) {
    if (getFromDB('options', 'stop_board') === 1) return 'Постинг приостановлен';
    if (!isset($_POST['captcha'], $_POST['verify'])) return 'Необходимо решить капчу';
    if (isset($_POST['password']) && mb_strlen($_POST['password']) > 100) return 'Пароль не должен превышать 100 символов';
    $db = connectDB();
    if ($parent !== 0) {
        $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE id = :id AND parent = 0 AND status = 0");
        $stmt->execute(['id' => $parent]);
        if ($stmt->fetchColumn() === 0) return 'Такого треда не существует';
    }
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE verify = :verify ORDER BY id DESC LIMIT 100");
    $stmt->execute(['verify' => $_POST['verify']]);
    if ($stmt->fetchColumn() > 0) return 'Капча уже использована';
    if (hash_hmac('sha256', mb_strtolower($_POST['captcha'], 'UTF-8'), getFromDB('options', 'password') . date('YmdH')) !== $_POST['verify']) return 'Капча введена неверно';
    if ($parent !== 0 && trim(preg_replace('/\[(s|sp|i)\]([^\[]*)\[\/\1\]/', '$2', $_POST['message'])) === '' && empty($_FILES['files']['name'][0])) return 'Ответ должен содержать сообщение или файл';
    $messageValidation = validateMessage($_POST['message']);
    if ($messageValidation !== 0) return [1 => 'Ваше сообщение превышает лимит символов', 2 => 'Ваш пост не прошёл фильтр от вайпа'][$messageValidation];
    $fileValidation = validateFiles($_FILES['files']);
    if ($fileValidation !== 0) {
        $errors = [1 => 'Для создания треда нужно прикрепить файл', 2 => 'Разрешено прикрепление не более 4 файлов', 3 => 'Поддерживаются только файлы формата: JPG, PNG, GIF, MP4 и WEBM', 4 => 'Прикреплён повреждённый файл или произошла ошибка при загрузке', 5 => 'Общий размер прикреплённых файлов превышает лимит', 6 => 'Ваш пост не прошёл фильтр от вайпа'];
        if ($fileValidation === 1 && $parent !== 0) $fileValidation = 0;
        if ($fileValidation !== 0) return $errors[$fileValidation];
    }
    $statusTime = time();
    if ($parent !== 0) {
        $statusTime = (int)(substr($statusTime, 0, -1) . '0');
        $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE status_time = :status_time AND parent != 0");
    } else {
        $statusTime = (int)(substr($statusTime, 0, -2) . '00');
        $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE status_time = :status_time AND parent = 0");
    }
    $stmt->execute(['status_time' => $statusTime]);
    if ($stmt->fetchColumn() > 0) return 'Скорость постинга ограничена';
    $uploadedFiles = uploadFiles($_FILES['files']);
    $id = getFromDB('posts', 'id') === false ? getFromDB('options', 'id') + 1 : getFromDB('posts', 'id') + 1;
    if ($parent !== 0) {
        $bumpLimit = getFromDB('options', 'bump_limit');
        $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE parent = :parent AND status = 0");
        $stmt->execute(['parent' => $parent]);
        if ($stmt->fetchColumn() >= $bumpLimit) $_POST['sage'] = 1;
    }
    $newPost = ['id' => (int)$id, 'parent' => (int)$parent, 'sage' => isset($_POST['sage']) ? 1 : 0, 'time' => substr_replace(date('d/m/y H:i'), 'X', -1), 'message' => !empty($_POST['message']) ? transformMessage($_POST['message']) : null, 'file1' => $uploadedFiles[0]['name'] ?? null, 'file1_info' => $uploadedFiles[0]['info'] ?? null, 'file2' => $uploadedFiles[1]['name'] ?? null, 'file2_info' => $uploadedFiles[1]['info'] ?? null, 'file3' => $uploadedFiles[2]['name'] ?? null, 'file3_info' => $uploadedFiles[2]['info'] ?? null, 'file4' => $uploadedFiles[3]['name'] ?? null, 'file4_info' => $uploadedFiles[3]['info'] ?? null, 'status' => 0, 'status_time' => $statusTime, 'password' => $parent === 0 ? (!empty($_POST['password']) ? password_hash($_POST['password'], PASSWORD_BCRYPT) : null) : null, 'verify' => $_POST['verify']];
    $stmt = $db->prepare('INSERT INTO posts (id, parent, sage, time, message, file1, file1_info, file2, file2_info, file3, file3_info, file4, file4_info, status, status_time, password, verify) VALUES (:id, :parent, :sage, :time, :message, :file1, :file1_info, :file2, :file2_info, :file3, :file3_info, :file4, :file4_info, :status, :status_time, :password, :verify)');
    $stmt->execute($newPost);
    $stmt = $db->prepare("UPDATE posts SET verify = NULL WHERE id NOT IN (SELECT id FROM (SELECT id FROM posts WHERE verify IS NOT NULL ORDER BY id DESC LIMIT 100) AS last_100)");
    $stmt->execute();
    manageThreadStatuses();
    if (rand(1, 100) === 1) cleanupFiles();
    return $id;
}

function handleModeration($db, $postIds, $password) {
    $statusTime = (int)(substr(time(), 0, -3) . '000');
    $moderated = false;
    if (password_verify($password, getFromDB('options', 'password'))) {
        $placeholders = implode(',', array_fill(0, count($postIds), '?'));
        $stmt = $db->prepare("UPDATE posts SET status = 1, status_time = ? WHERE id IN ($placeholders) OR parent IN ($placeholders)");
        $stmt->execute(array_merge([$statusTime], $postIds, $postIds));
        $moderated = true;
    } else {
        foreach ($postIds as $postId) {
            $stmt = $db->prepare("SELECT parent, password FROM posts WHERE id = ?");
            $stmt->execute([$postId]);
            $post = $stmt->fetch(PDO::FETCH_ASSOC);
            if ($post['parent'] === 0) {
                if (password_verify($password, $post['password'])) {
                    $stmt = $db->prepare("UPDATE posts SET status = 2, status_time = ? WHERE id = ? OR parent = ?");
                    $stmt->execute([$statusTime, $postId, $postId]);
                    $moderated = true;
                }
            } else {
                $stmt = $db->prepare("SELECT password FROM posts WHERE id = ?");
                $stmt->execute([$post['parent']]);
                $thread = $stmt->fetch(PDO::FETCH_ASSOC);
                if (!empty($thread['password']) && password_verify($password, $thread['password'])) {
                    $stmt = $db->prepare("UPDATE posts SET status = 2, status_time = ? WHERE id = ?");
                    $stmt->execute([$statusTime, $postId]);
                    $moderated = true;
                }
            }
        }
    }
    if ($moderated) manageThreadStatuses();
    return $moderated;
}

function getPostStats($db) {
    $now = time();
    $times = array_map(fn($t) => DateTime::createFromFormat('d/m/y H:i', str_replace('X', '0', $t))->getTimestamp(), $db->query("SELECT time FROM posts WHERE status IN (0, 3)")->fetchAll(PDO::FETCH_COLUMN));
    $lastMonth = count(array_filter($times, fn($t) => $t >= $now - 60 * 60 * 24 * 30));
    return ['lastHour' => count(array_filter($times, fn($t) => $t >= $now - 60 * 60)), 'lastDay' => count(array_filter($times, fn($t) => $t >= $now - 60 * 60 * 24)), 'avgPerHour' => round($lastMonth / (24 * 30), 1), 'avgPerDay' => round($lastMonth / 30, 1)];
}

function pageHeader($title, $headerContent) {
    return "<!DOCTYPE html>\n<html lang=\"ru\">\n\t<head>\n\t\t<meta charset=\"UTF-8\">\n\t\t<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\t\t<link rel=\"icon\" type=\"image/x-icon\" href=\"/favicon.ico\">\n\t\t<link rel=\"stylesheet\" type=\"text/css\" href=\"/assets/style.css\">\n\t\t<script type=\"text/javascript\" src=\"/assets/script.js\" defer></script>\n\t\t<title>Цукиба — {$title}</title>\n\t</head>\n\t<body>\n\t\t<header><a href=\"/\">Главная</a> | <a href=\"/catalog\">Каталог</a> | <a href=\"/modlog\">Модлог</a> | <a href=\"/info\">Инфо</a>{$headerContent}</header>\n\t\t";
}

function pageFooter() {
    return "\n\t</body>\n\t<!-- Tsukiba engine -->\n</html>";
}

function handlePostAction() {
    $result = handlePostSubmission((int)$_POST['parent'] ?? 0);
    if (is_numeric($result)) {
        $threadId = $_POST['parent'] ?: $result;
        $pageType = $_POST['page-type'] ?? 'normal';
        $path = $pageType === 'short' ? "/short/{$threadId}" : "/thread/{$threadId}";
        header("Location: {$path}#{$result}");
        exit;
    }
    http_response_code(400);
    return pageHeader('Ошибка', '') . "<div class=\"info-page\">{$result}</div>" . pageFooter();
}

function handleModAction() {
    if (empty($_POST['mod-box'])) {
        http_response_code(400);
        return pageHeader('Ошибка', '') . '<div class="info-page">Вы ничего не выбрали</div>' . pageFooter();
    }
    if (empty($_POST['mod-pass'])) {
        http_response_code(400);
        return pageHeader('Ошибка', '') . '<div class="info-page">Вы не ввели пароль</div>' . pageFooter();
    }
    if (mb_strlen($_POST['mod-pass']) > 100) return 'Пароль не должен превышать 100 символов';
    $db = connectDB();
    $result = handleModeration($db, $_POST['mod-box'], $_POST['mod-pass']);
    if ($result) {
        header('Location: ' . ($_POST['return-url'] ?? '/'));
        exit;
    }
    http_response_code(400);
    return pageHeader('Ошибка', '') . '<div class="info-page">Неверный пароль</div>' . pageFooter();
}

function indexPage($page = 0) {
    $db = connectDB();
    $page = max(0, intval($page));
    $threadsPerPage = 20;
    $totalThreads = count(getThreads());
    $totalPages = max(1, ceil($totalThreads / $threadsPerPage));
    if ($page >= $totalPages) return errorPage();
    $offset = $page * $threadsPerPage;
    $paginationLinks = [];
    for ($i = 0; $i < $totalPages; $i++) $paginationLinks[] = $i === $page ? "<span>{$i}</span>" : ($i === 0 ? "<a href=\"/\">{$i}</a>" : "<a href=\"/{$i}\">{$i}</a>");
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE parent = 0 AND status = 3");
    $stmt->execute();
    $archiveLink = $stmt->fetchColumn() > 0 ? ", <a href=\"/archive\">Архив</a>" : '';
    $headerContent = " | <a href=\"#postform\">Новый пост</a> | Страница: " . implode(', ', $paginationLinks) . $archiveLink;
    $threads = getThreads($threadsPerPage, $offset);
    $requestUri = htmlspecialchars($_SERVER['REQUEST_URI']);
    $showThreads = "\n\t\t<div class=\"index-page\">\n\t\t\t<a id=\"mod\"></a>\n\t\t\t<form method=\"post\" action=\"/mod\">\n\t\t\t\t<input type=\"hidden\" name=\"return-url\" value=\"{$requestUri}\">\n\t\t\t\t<div class=\"mod-form\">\n\t\t\t\t\t<a class=\"close-button mod-close\" href=\"##\">×</a>\n\t\t\t\t\t<input class=\"mod-pass\" type=\"password\" name=\"mod-pass\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t\t<input class=\"mod-submit\" type=\"submit\" value=\"Удалить\">\n\t\t\t\t</div>";
    if (!empty($threads)) {
        $generateThread = array_map(function($thread) use ($db) {
            $generate = "\n\t\t\t\t<div id=\"thread-{$thread['id']}\" class=\"thread-container\">" . generateThread($thread);
            $stmt = $db->prepare("SELECT * FROM posts WHERE parent = :threadId AND status = 0 ORDER BY id DESC LIMIT 3");
            $stmt->execute(['threadId' => $thread['id']]);
            $replies = array_reverse($stmt->fetchAll(PDO::FETCH_ASSOC));
            $omittedReplies = countReplies($thread['id']) - count($replies);
            if ($omittedReplies > 0) $generate .= "\n\t\t\t\t\t<div class=\"omitted-posts\">Пропущено ответов: {$omittedReplies}. Откройте тред, чтобы посмотреть.</div>";
            foreach ($replies as $reply) $generate .= generatePost($reply);
            return $generate . "\n\t\t\t\t</div>";
        }, $threads);
        $showThreads .= implode("\n\t\t\t\t<hr>", $generateThread);
    }
    $showThreads .= "\n\t\t\t</form>\n\t\t</div>";
    return pageHeader('Главная', $headerContent) . generatePostForm() . $showThreads . pageFooter();
}

function threadPage($threadId) {
    $db = connectDB();
    if (!is_numeric($threadId) || $threadId <= 0) return errorPage();
    $stmt = $db->prepare("SELECT * FROM posts WHERE (id = :id OR parent = :id) AND (status = 0 OR status = 3) ORDER BY id ASC");
    $stmt->execute(['id' => $threadId]);
    $posts = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (empty($posts) || $posts[0]['parent'] !== 0) return errorPage();
    if ($posts[0]['status'] === 3) {
        header("Location: /archived/{$threadId}");
        exit;
    }
    $thread = $posts[0];
    $threadTitle = truncateString(strip_tags(str_replace('<br>', ' ', $thread['message'] ?? '')), 50);
    $replyCount = countReplies($threadId);
    $requestUri = htmlspecialchars($_SERVER['REQUEST_URI']);
    $showPosts = "\n\t\t<div class=\"thread-page\">\n\t\t\t<a id=\"mod\"></a>\n\t\t\t<form method=\"post\" action=\"/mod\">\n\t\t\t\t<input type=\"hidden\" name=\"return-url\" value=\"{$requestUri}\">\n\t\t\t\t<div class=\"mod-form\">\n\t\t\t\t\t<a class=\"close-button mod-close\" href=\"##\">×</a>\n\t\t\t\t\t<input class=\"mod-pass\" type=\"password\" name=\"mod-pass\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t\t<input class=\"mod-submit\" type=\"submit\" value=\"Удалить\">\n\t\t\t\t</div>\n\t\t\t\t<div id=\"thread-{$threadId}\" class=\"thread-container\">" . generateThread($thread, true);
    foreach (array_slice($posts, 1) as $post) $showPosts .= generatePost($post, true);
    $showPosts .= "\n\t\t\t\t</div>\n\t\t\t</form>\n\t\t</div>";
    return pageHeader("{$threadTitle}", " | <a href=\"#postform\">Новый пост</a> | Ответов: {$replyCount}") . generatePostForm($threadId) . $showPosts . pageFooter();
}

function shortPage($threadId) {
    $db = connectDB();
    if (!is_numeric($threadId) || $threadId <= 0) return errorPage();
    $stmt = $db->prepare("SELECT * FROM posts WHERE id = :id AND parent = 0 AND status = 0");
    $stmt->execute(['id' => $threadId]);
    $thread = $stmt->fetch(PDO::FETCH_ASSOC);
    $replyCount = countReplies($threadId);
    if (!$thread || $replyCount < 100) {
        header("Location: /thread/{$threadId}");
        exit;
    }
    $stmt = $db->prepare("SELECT * FROM posts WHERE parent = :id AND status = 0 ORDER BY id DESC LIMIT 50");
    $stmt->execute(['id' => $threadId]);
    $replies = array_reverse($stmt->fetchAll(PDO::FETCH_ASSOC));
    $omittedPosts = $replyCount - count($replies);
    $threadTitle = truncateString(strip_tags(str_replace('<br>', ' ', $thread['message'] ?? '')), 50);
    $shortThreadPosts = array_merge([$thread['id']], array_column($replies, 'id'));
    $requestUri = htmlspecialchars($_SERVER['REQUEST_URI']);
    $showPosts = "\n\t\t<div class=\"short-page thread-page\">\n\t\t\t<a id=\"mod\"></a>\n\t\t\t<form method=\"post\" action=\"/mod\">\n\t\t\t\t<input type=\"hidden\" name=\"return-url\" value=\"{$requestUri}\">\n\t\t\t\t<div class=\"mod-form\">\n\t\t\t\t\t<a class=\"close-button mod-close\" href=\"##\">×</a>\n\t\t\t\t\t<input class=\"mod-pass\" type=\"password\" name=\"mod-pass\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t\t<input class=\"mod-submit\" type=\"submit\" value=\"Удалить\">\n\t\t\t\t</div>\n\t\t\t\t<div id=\"thread-{$threadId}\" class=\"thread-container\">" . generateThread($thread, true, 2);
    if ($omittedPosts > 0) $showPosts .= "\n\t\t\t\t\t<div class=\"omitted-posts\">Пропущено ответов: {$omittedPosts}. Откройте <a href=\"/thread/{$threadId}\">полный тред</a>, чтобы посмотреть.</div>";
    foreach ($replies as $reply) $showPosts .= generatePost($reply, true, 2);
    $showPosts .= "\n\t\t\t\t</div>\n\t\t\t</form>\n\t\t</div>";
    $showPosts = replaceShortPageLinks($showPosts, $threadId, $shortThreadPosts);
    return pageHeader("{$threadTitle}", " | <a href=\"#postform\">Новый пост</a> | Ответов: {$replyCount}") . generatePostForm($threadId, 'short') . $showPosts . pageFooter();
}

function catalogPage() {
    $search = isset($_GET['search']) ? htmlspecialchars($_GET['search']) : '';
    $threads = getThreads();
    $catalogItems = '';
    $counter = 0;
    foreach ($threads as $thread) {
        if ($search !== '' && !searchInThread($thread['id'], $search)) continue;
        $counter++;
        $replyCount = countReplies($thread['id']);
        $videoThumb = in_array(pathinfo($thread['file1'], PATHINFO_EXTENSION), ['mp4', 'webm']) ? ' video-thumb' : '';
        $fileHash = pathinfo($thread['file1'], PATHINFO_FILENAME);
        $thumb = $fileHash . '.webp';
        $subdir = getSubdirPath($fileHash);
        $opModIndicator = $thread['password'] ? ' <span class="op-mod-indicator" title="ОП-модерация">(М)</span>' : '';
        $catalogItems .= "\n\t\t\t<div id=\"thread-{$thread['id']}\" class=\"catalog-thread\" tabindex=\"{$counter}\">\n\t\t\t\t<a href=\"/thread/{$thread['id']}\"><img class=\"catalog-thumb{$videoThumb}\" src=\"/thumb/{$subdir}/{$thumb}\" loading=\"lazy\"></a>\n\t\t\t\t<div class=\"catalog-reply-count\">Ответов: {$replyCount}{$opModIndicator}</div>\n\t\t\t\t<div class=\"catalog-message\">{$thread['message']}</div>\n\t\t\t</div>";
    }
    return pageHeader('Каталог', " | <form class=\"search-form\" method=\"get\"><input class=\"search-input\" type=\"text\" name=\"search\" placeholder=\"Поиск\" value=\"{$search}\"></form>") . "<div class=\"catalog-page\">{$catalogItems}\n\t\t</div>" . pageFooter();
}

function infoPage() {
    $maxFileSize = readableBytes(getFromDB('options', 'max_file_size'));
    $bumpLimit = getFromDB('options', 'bump_limit');
    $maxThreads = getFromDB('options', 'max_threads');
    return pageHeader('Инфо', '') . "<div class=\"info-page\"><b>Разметка</b><br>Ответ: <post-link>&gt;&gt;номер поста</post-link><br>Цитата: <span class=\"quote\">&gt;текст с новой строки</span><br>Спойлер: [sp]<span class=\"spoiler\">текст</span>[/sp]<br>Зачёркнутый: [s]<s>текст</s>[/s]<br>Наклонный: [i]<i>текст</i>[/i]<br><br><b>Технические данные</b><br>Поддерживаются файлы формата: JPG, PNG, GIF, MP4 и WEBM<br>Максимальный общий размер файлов: {$maxFileSize}<br>Ответов до бамплимита: {$bumpLimit}<br>Максимальное число активных тредов: {$maxThreads}</div>" . pageFooter();
}

function archivePage($page = 0) {
    $db = connectDB();
    $page = max(0, intval($page));
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE parent = 0 AND status = 3");
    $stmt->execute();
    $totalThreads = $stmt->fetchColumn();
    if ($totalThreads === 0) return errorPage();
    $threadsPerPage = 50;
    $totalPages = max(1, ceil($totalThreads / $threadsPerPage));
    if ($page >= $totalPages) return errorPage();
    $stmt = $db->prepare("SELECT t.*, MAX(CASE WHEN r.sage = 1 THEN t.id ELSE COALESCE(r.id, t.id) END) as last_bump FROM posts t LEFT JOIN posts r ON t.id = r.parent AND r.status = 3 WHERE t.parent = 0 AND t.status = 3 GROUP BY t.id ORDER BY last_bump DESC LIMIT :limit OFFSET :offset");
    $stmt->bindValue(':limit', $threadsPerPage, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $page * $threadsPerPage, PDO::PARAM_INT);
    $stmt->execute();
    $threads = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $paginationLinks = [];
    for ($i = 0; $i < $totalPages; $i++) $paginationLinks[] = $i === $page ? "<span>{$i}</span>" : ($i === 0 ? "<a href=\"/archive\">0</a>" : "<a href=\"/archive/{$i}\">{$i}</a>");
    $catalogItems = '';
    foreach ($threads as $counter => $thread) {
        $replyCount = countReplies($thread['id']);
        $videoThumb = in_array(pathinfo($thread['file1'], PATHINFO_EXTENSION), ['mp4', 'webm']) ? ' video-thumb' : '';
        $fileHash = pathinfo($thread['file1'], PATHINFO_FILENAME);
        $thumb = $fileHash . '.webp';
        $subdir = getSubdirPath($fileHash);
        $opModIndicator = $thread['password'] ? ' <span class="op-mod-indicator" title="ОП-модерация">(М)</span>' : '';
        $catalogItems .= "\n\t\t\t<div id=\"thread-{$thread['id']}\" class=\"catalog-thread\" tabindex=\"" . ($counter + 1) . "\">\n\t\t\t\t<a href=\"/archived/{$thread['id']}\"><img class=\"catalog-thumb{$videoThumb}\" src=\"/thumb/{$subdir}/{$thumb}\" loading=\"lazy\"></a>\n\t\t\t\t<div class=\"catalog-reply-count\">Ответов: {$replyCount}{$opModIndicator}</div>\n\t\t\t\t<div class=\"catalog-message\">{$thread['message']}</div>\n\t\t\t</div>";
    }
    return pageHeader('Архив', " | <a href=\"/archive\">Архив</a> | Страница: " . implode(', ', $paginationLinks)) . "<div class=\"archive-page\">{$catalogItems}\n\t\t</div>" . pageFooter();
}

function archivedThreadPage($threadId) {
    $db = connectDB();
    if (!is_numeric($threadId) || $threadId <= 0) return errorPage();
    $stmt = $db->prepare("SELECT * FROM posts WHERE (id = :id OR parent = :id) AND (status = 0 OR status = 3) ORDER BY id ASC");
    $stmt->execute(['id' => $threadId]);
    $posts = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (empty($posts) || $posts[0]['parent'] !== 0) return errorPage();
    if ($posts[0]['status'] === 0) {
        header("Location: /thread/{$threadId}");
        exit;
    }
    $thread = $posts[0];
    $threadTitle = truncateString(strip_tags(str_replace('<br>', ' ', $thread['message'] ?? '')), 50);
    $replyCount = countReplies($threadId);
    $showPosts = "<div class=\"archived-page\">\n\t\t\t<div class=\"thread-page\">\n\t\t\t\t<div id=\"thread-{$threadId}\" class=\"thread-container\">" . generateThread($thread, true, 3);
    foreach (array_slice($posts, 1) as $post) $showPosts .= generatePost($post, true, 3);
    $showPosts .= "\n\t\t\t\t</div>\n\t\t\t</div>\n\t\t</div>";
    return pageHeader("{$threadTitle}", " | <a href=\"/archive\">Архив</a> | Ответов: {$replyCount}") . $showPosts . pageFooter();
}

function modLogPage($page = 0) {
    $db = connectDB();
    $page = max(0, intval($page));
    $postsPerPage = 50;
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE status IN (1, 2)");
    $stmt->execute();
    $totalPosts = $stmt->fetchColumn();
    $totalPages = max(1, ceil($totalPosts / $postsPerPage));
    if ($page >= $totalPages) return errorPage();
    $stmt = $db->prepare("SELECT p.*, CASE WHEN p.parent = 0 THEN p.status ELSE (SELECT status FROM posts WHERE id = p.parent) END AS thread_status FROM posts p WHERE p.status IN (1, 2) ORDER BY p.id DESC LIMIT :limit OFFSET :offset");
    $stmt->bindValue(':limit', $postsPerPage, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $page * $postsPerPage, PDO::PARAM_INT);
    $stmt->execute();
    $deletedPosts = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $paginationLinks = [];
    for ($i = 0; $i < $totalPages; $i++) $paginationLinks[] = $i === $page ? "<span>{$i}</span>" : ($i === 0 ? "<a href=\"/modlog\">0</a>" : "<a href=\"/modlog/{$i}\">{$i}</a>");
    $body = "<div class=\"modlog-page\">\n\t\t\t<a id=\"mod\"></a>\n\t\t\t<form method=\"post\">\n\t\t\t\t<div class=\"mod-form\">\n\t\t\t\t\t<a class=\"close-button mod-close\" href=\"##\">×</a>\n\t\t\t\t\t<input class=\"mod-pass\" type=\"password\" name=\"mod-pass\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t\t<input class=\"mod-submit\" type=\"submit\" value=\"Восстановить\">\n\t\t\t\t</div>";
    foreach ($deletedPosts as $post) {
        $isThread = $post['parent'] === 0;
        $deletedBy = $post['status'] === 1 ? 'администратором' : 'ОП-ом';
        $threadId = $isThread ? $post['id'] : $post['parent'];
        $threadStatus = $post['thread_status'];
        $threadNumber = ($threadStatus === 0 || $threadStatus === 3) ? "<a href=\"" . ($threadStatus === 0 ? "/thread/{$threadId}" : "/archived/{$threadId}") . "\">№{$threadId}</a>" : "<s title=\"Тред удалён\">№{$threadId}</s>";
        $legendText = $isThread ? "Тред {$threadNumber}, удалён {$deletedBy}" : "Ответ в треде {$threadNumber}, удалён {$deletedBy}";
        $body .= "\n\t\t\t\t<fieldset>\n\t\t\t\t\t<legend>{$legendText}</legend>" . ($isThread ? generateThread($post, true, 1) : generatePost($post, true, 1)) . "\n\t\t\t\t</fieldset>";
    }
    $body .= "\n\t\t\t</form>\n\t\t</div>";
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        $password = $_POST['mod-pass'];
        $postsToRestore = $_POST['mod-box'] ?? [];
        if (empty($postsToRestore)) {
            http_response_code(400);
            return pageHeader('Ошибка', '') . '<div class="info-page">Вы ничего не выбрали</div>' . pageFooter();
        }
        $restoredCount = 0;
        $isAdminPassword = password_verify($password, getFromDB('options', 'password'));
        foreach ($postsToRestore as $postId) {
            $stmt = $db->prepare("SELECT parent, password, status FROM posts WHERE id = ?");
            $stmt->execute([$postId]);
            $post = $stmt->fetch(PDO::FETCH_ASSOC);
            $canRestore = $isAdminPassword;
            if (!$canRestore && $post['parent'] === 0 && $post['status'] === 2) $canRestore = password_verify($password, strval($post['password']));
            elseif (!$canRestore && $post['parent'] !== 0) {
                $stmt = $db->prepare("SELECT password FROM posts WHERE id = ?");
                $stmt->execute([$post['parent']]);
                $parentThread = $stmt->fetch(PDO::FETCH_ASSOC);
                $canRestore = password_verify($password, strval($parentThread['password']));
            }
            if ($canRestore) {
                if ($post['parent'] === 0) {
                    $stmt = $db->prepare("UPDATE posts SET status = 0 WHERE id = ? OR parent = ?");
                    $stmt->execute([$postId, $postId]);
                    $restoredCount++;
                } else {
                    $stmt = $db->prepare("SELECT status FROM posts WHERE id = ?");
                    $stmt->execute([$post['parent']]);
                    if ($stmt->fetchColumn() === 0) {
                        $stmt = $db->prepare("UPDATE posts SET status = 0 WHERE id = ?");
                        $stmt->execute([$postId]);
                        $restoredCount++;
                    }
                }
            }
        }
        if ($restoredCount > 0) {
            manageThreadStatuses();
            header('Location: /modlog');
            exit;
        } else {
            http_response_code(400);
            return pageHeader('Ошибка', '') . '<div class="info-page">Неверный пароль или нет постов для восстановления</div>' . pageFooter();
        }
    }
    return pageHeader('Модлог', " | Страница: " . implode(', ', $paginationLinks)) . $body . pageFooter();
}

function managePage($page = 0) {
    $manageKey = 'secretkey';
    if (!isset($_GET['key']) || $_GET['key'] !== $manageKey) return errorPage();
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        $validActions = ['initial_setup', 'setup'];
        if (!in_array($_POST['action'], $validActions) || !ctype_digit((string)$_POST['max_file_size']) || !ctype_digit((string)$_POST['bump_limit']) || !ctype_digit((string)$_POST['max_threads']) || !ctype_digit((string)$_POST['max_message_length']) || $_POST['captcha'] === '' || !ctype_digit((string)$_POST['stop_board'])) {
            http_response_code(400);
            return pageHeader('Ошибка', '') . '<div class="info-page">Не все поля заполнены</div>' . pageFooter();
        }
        $_POST['max_file_size'] = (int)($_POST['max_file_size'] * 1024 * 1024);
        if ($_POST['action'] === 'initial_setup') {
            if ($_POST['password'] !== $_POST['confirm_password']) {
                http_response_code(400);
                return pageHeader('Ошибка', '') . '<div class="info-page">Пароль не совпадает</div>' . pageFooter();
            }
            $options = ['max_file_size' => (int)$_POST['max_file_size'], 'bump_limit' => (int)$_POST['bump_limit'], 'max_threads' => (int)$_POST['max_threads'], 'max_message_length' => (int)$_POST['max_message_length'], 'captcha' => $_POST['captcha'], 'id' => ctype_digit($_POST['id']) ? (int)$_POST['id'] : 0, 'stop_board' => $_POST['stop_board'], 'password' => password_hash($_POST['password'], PASSWORD_BCRYPT)];
            $db = connectDB();
            createTables($db);
            saveOptions($db, $options);
            !is_dir('media') ? mkdir('media', 0777, true) : null;
            !is_dir('thumb') ? mkdir('thumb', 0777, true) : null;
            header('Refresh: 0');
            return '';
        } else {
            if (!password_verify($_POST['password'], getFromDB('options', 'password'))) {
                http_response_code(400);
                return pageHeader('Ошибка', '') . '<div class="info-page">Пароль введён неверно</div>' . pageFooter();
            }
            if ($_POST['new_password'] !== $_POST['confirm_new_password']) {
                http_response_code(400);
                return pageHeader('Ошибка', '') . '<div class="info-page">Новый пароль не совпадает</div>' . pageFooter();
            }
            $newPassword = $_POST['new_password'] === '' ? getFromDB('options', 'password') : password_hash($_POST['new_password'], PASSWORD_BCRYPT);
            $options = ['max_file_size' => (int)$_POST['max_file_size'], 'bump_limit' => (int)$_POST['bump_limit'], 'max_threads' => (int)$_POST['max_threads'], 'max_message_length' => (int)$_POST['max_message_length'], 'captcha' => $_POST['captcha'], 'id' => getFromDB('options', 'id'), 'stop_board' => $_POST['stop_board'], 'password' => $newPassword];
            $db = connectDB();
            updateOptions($db, $options);
            manageThreadStatuses();
            header('Refresh: 0');
            return '';
        }
    }
    $captchaTypes = [['value' => 'simple', 'label' => 'Простая'], ['value' => 'shadow', 'label' => 'Тени']];
    if (!dbExist()) {
        $captchaOptions = '';
        foreach ($captchaTypes as $type) $captchaOptions .= "\n\t\t\t\t\t<option value=\"{$type['value']}\">Капча: {$type['label']}</option>";
        return pageHeader('Управление', '') . "<div class=\"manage-page\">\n\t\t\t<form class=\"manage-form\" method=\"post\" action=\"/manage?key={$manageKey}\">\n\t\t\t\t<input type=\"hidden\" name=\"action\" value=\"initial_setup\">\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_file_size\" placeholder=\"Максимальный общий размер файлов в Мб\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"bump_limit\" placeholder=\"Ответов до бамплимита\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_threads\" placeholder=\"Максимальное число активных тредов\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_message_length\" placeholder=\"Максимальная длина сообщения\"><br>\n\t\t\t\t<select class=\"manage-input\" name=\"captcha\">{$captchaOptions}\n\t\t\t\t</select><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"id\" placeholder=\"Пропустить столько постов. 0: не пропускать.\"><br>\n\t\t\t\t<input class=\"manage-pass\" type=\"password\" name=\"password\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t<input class=\"manage-pass-check\" type=\"password\" name=\"confirm_password\" maxlength=\"100\" placeholder=\"Проверка\"><br>\n\t\t\t\t<input class=\"manage-submit\" type=\"submit\" value=\"Сохранить\">\n\t\t\t\t<input type=\"hidden\" name=\"stop_board\" value=\"0\">\n\t\t\t\t<label><input class=\"stop-board\" type=\"checkbox\" name=\"stop_board\" value=\"1\"> Остановить доску</label>\n\t\t\t</form>\n\t\t</div>" . pageFooter();
    }
    $db = connectDB();
    $page = max(0, intval($page));
    $postsPerPage = 50;
    $stmt = $db->prepare("SELECT COUNT(*) FROM posts WHERE status = 0");
    $stmt->execute();
    $totalPosts = $stmt->fetchColumn();
    $totalPages = max(1, ceil($totalPosts / $postsPerPage));
    if ($page >= $totalPages) $page = $totalPages - 1;
    $offset = $page * $postsPerPage;
    $stmt = $db->prepare("SELECT * FROM posts WHERE status = 0 ORDER BY id DESC LIMIT :limit OFFSET :offset");
    $stmt->bindValue(':limit', $postsPerPage, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    $stmt->execute();
    $activePosts = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $paginationLinks = [];
    for ($i = 0; $i < $totalPages; $i++) $paginationLinks[] = $i === $page ? "<span>{$i}</span>" : ($i === 0 ? "<a href=\"/manage?key={$manageKey}\">0</a>" : "<a href=\"/manage/{$i}?key={$manageKey}\">{$i}</a>");
    $headerContent = " | Страница: " . implode(', ', $paginationLinks);
    $body = '<div class="manage-page">';
    if ($page === 0) {
        $pasteMaxFileSize = getFromDB('options', 'max_file_size') / (1024 * 1024);
        $pasteBumpLimit = getFromDB('options', 'bump_limit');
        $pasteMaxThreads = getFromDB('options', 'max_threads');
        $pasteMaxMessageLength = getFromDB('options', 'max_message_length');
        $checkStopBoard = (getFromDB('options', 'stop_board') === 1) ? ' checked' : '';
        $captchaType = getFromDB('options', 'captcha');
        $stats = getPostStats($db);
        $captchaOptions = '';
        foreach ($captchaTypes as $type) {
            $selected = ($captchaType === $type['value']) ? ' selected' : '';
            $captchaOptions .= "\n\t\t\t\t\t<option value=\"{$type['value']}\"{$selected}>Капча: {$type['label']}</option>";
        }
        $body .= "\n\t\t\t<form class=\"manage-form\" method=\"post\" action=\"/manage?key={$manageKey}\">\n\t\t\t\t<input type=\"hidden\" name=\"action\" value=\"setup\">\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_file_size\" value=\"{$pasteMaxFileSize}\" placeholder=\"Максимальный общий размер файлов в Мб\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"bump_limit\" value=\"{$pasteBumpLimit}\" placeholder=\"Ответов до бамплимита\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_threads\" value=\"{$pasteMaxThreads}\" placeholder=\"Максимальное число активных тредов\"><br>\n\t\t\t\t<input class=\"manage-input\" type=\"text\" name=\"max_message_length\" value=\"{$pasteMaxMessageLength}\" placeholder=\"Максимальная длина сообщения\"><br>\n\t\t\t\t<select class=\"manage-input\" name=\"captcha\">{$captchaOptions}\n\t\t\t\t</select><br>\n\t\t\t\t<input class=\"manage-pass\" type=\"password\" name=\"new_password\" maxlength=\"100\" placeholder=\"Новый пароль\">\n\t\t\t\t<input class=\"manage-pass-check\" type=\"password\" name=\"confirm_new_password\" maxlength=\"100\" placeholder=\"Проверка\"><br>\n\t\t\t\t<input class=\"pass\" type=\"password\" name=\"password\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t<input class=\"manage-submit\" type=\"submit\" value=\"Сохранить\">\n\t\t\t\t<input type=\"hidden\" name=\"stop_board\" value=\"0\">\n\t\t\t\t<label><input class=\"stop-board\" type=\"checkbox\" name=\"stop_board\" value=\"1\"{$checkStopBoard}> Остановить доску</label>\n\t\t\t</form>\n\t\t\t<div class=\"stats\">Постов за час:&nbsp;{$stats['lastHour']}, за день:&nbsp;{$stats['lastDay']}, в час:&nbsp;{$stats['avgPerHour']}, в день:&nbsp;{$stats['avgPerDay']}</div>";
    }
    $requestUri = htmlspecialchars($_SERVER['REQUEST_URI']);
    $body .= "\n\t\t\t<a id=\"mod\"></a>\n\t\t\t<form class=\"manage-mod\" method=\"post\" action=\"/mod\">\n\t\t\t\t<input type=\"hidden\" name=\"return-url\" value=\"{$requestUri}\">\n\t\t\t\t<div class=\"mod-form\">\n\t\t\t\t\t<a class=\"close-button mod-close\" href=\"##\">×</a>\n\t\t\t\t\t<input class=\"mod-pass\" type=\"password\" name=\"mod-pass\" maxlength=\"100\" placeholder=\"Пароль\">\n\t\t\t\t\t<input class=\"mod-submit\" type=\"submit\" value=\"Удалить\">\n\t\t\t\t</div>";
    foreach ($activePosts as $post) {
        $isThread = $post['parent'] === 0;
        $legendText = $isThread ? "Тред <a href=\"/thread/{$post['id']}\">№{$post['id']}</a>" : "Ответ в треде <a href=\"/thread/{$post['parent']}\">№{$post['parent']}</a>";
        $body .= "\n\t\t\t\t<fieldset>\n\t\t\t\t\t<legend>{$legendText}</legend>" . ($isThread ? generateThread($post) : generatePost($post)) . "\n\t\t\t\t</fieldset>";
    }
    $body .= "\n\t\t\t</form>\n\t\t</div>";
    return pageHeader('Управление', $headerContent) . $body . pageFooter();
}

function apiSubmitPost() {
    if (isset($_FILES['files']) && !is_array($_FILES['files']['name'])) $_FILES['files'] = ['name' => [$_FILES['files']['name']], 'type' => [$_FILES['files']['type']], 'tmp_name' => [$_FILES['files']['tmp_name']], 'error' => [$_FILES['files']['error']], 'size' => [$_FILES['files']['size']]];
    $result = handlePostSubmission((int)($_POST['parent'] ?? 0));
    if (is_numeric($result)) return ['post_id' => $result];
    http_response_code(400);
    return ['error' => $result];
}

function apiHandler() {
    header('Content-Type: application/json; charset=utf-8');
    $method = $_SERVER['REQUEST_METHOD'];
    $path = rtrim(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), '/');
    switch ($path) {
        case '/api':
            header('Content-Type: text/html');
            echo pageHeader('API', '') . '<div class="info-page"><b>GET</b><br>Список тредов: /api/index<br>Тред: /api/thread/{id}<br>Пост: /api/id/{id}<br>Параметры: /api/info<br>Капча: /api/post<br><br><b>POST</b> (/api/post)<br>Ответ в (0 — новый тред): parent<br>Не поднимать тред: sage<br>Сообщение: message<br>Файлы: files[]<br>Капча: captcha<br>Проверка капчи: verify<br></div>' . pageFooter();
            break;
        case '/api/index':
            if ($method === 'GET') echo json_encode(getActiveThreadsList(), JSON_UNESCAPED_UNICODE);
            break;
        case (preg_match('/^\/api\/thread\/(\d+)$/', $path, $matches) ? $path : !$path):
            if ($method === 'GET') {
                $threadContents = getThreadContents($matches[1]);
                if (empty($threadContents) || $matches[1] === 0) {
                    http_response_code(404);
                    echo json_encode(['error' => 'Страница не найдена'], JSON_UNESCAPED_UNICODE);
                } else echo json_encode($threadContents, JSON_UNESCAPED_UNICODE);
            }
            break;
        case (preg_match('/^\/api\/id\/(\d+)$/', $path, $matches) ? $path : !$path):
            if ($method === 'GET') {
                $post = getPostInfo($matches[1]);
                if (!$post) {
                    http_response_code(404);
                    echo json_encode(['error' => 'Страница не найдена'], JSON_UNESCAPED_UNICODE);
                } else echo json_encode($post, JSON_UNESCAPED_UNICODE);
            }
            break;
        case '/api/post':
            if ($method === 'GET') echo json_encode(generateApiCaptcha());
            elseif ($method === 'POST') echo json_encode(apiSubmitPost(), JSON_UNESCAPED_UNICODE);
            break;
        case '/api/info':
            if ($method === 'GET') echo json_encode(['max_file_size' => getFromDB('options', 'max_file_size'), 'max_message_length' => getFromDB('options', 'max_message_length')]);
            break;
        default:
            http_response_code(404);
            echo json_encode(['error' => 'Страница не найдена'], JSON_UNESCAPED_UNICODE);
    }
}

function errorPage() {
    http_response_code(404);
    return pageHeader('Ошибка', '') . '<div class="info-page">Страница не найдена</div>' . pageFooter();
}

function boardPages() {
    $path = rtrim(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), '/');
    if (!dbExist() && $path !== '/manage') return errorPage();
    switch ($path) {
        case '': case (preg_match('/^\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return indexPage($matches[1] ?? 0);
        case (preg_match('/^\/thread\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return threadPage($matches[1]);
        case (preg_match('/^\/short\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return shortPage($matches[1]);
        case '/catalog': return catalogPage();
        case '/info': return infoPage();
        case '/archive': case (preg_match('/^\/archive\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return archivePage($matches[1] ?? 0);
        case (preg_match('/^\/archived\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return archivedThreadPage($matches[1]);
        case '/modlog': case (preg_match('/^\/modlog\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return modLogPage($matches[1] ?? 0);
        case '/manage': case (preg_match('/^\/manage\/([1-9]\d*)$/', $path, $matches) ? $path : !$path): return managePage($matches[1] ?? 0);
        case '/post': return handlePostAction();
        case '/mod': return handleModAction();
        case (preg_match('/^\/api(\/|$)/', $path) ? $path : !$path): return apiHandler();
        case '/404': return errorPage();
        default: return errorPage();
    }
}

echo boardPages();
