"""
Модуль для взаимодействия с API Open edX (LMS).
"""

import logging
from typing import Any, Dict, Optional

from pymemcache.client import base as memcache
from requests.exceptions import ConnectionError, Timeout
from edx_rest_api_client.client import EdxRestApiClient
from edx_rest_api_client.exceptions import HttpClientError, SlumberBaseException

from xapi_bridge import constants, exceptions, settings


logger = logging.getLogger(__name__)


class BaseLMSAPIClient:
    """Базовый клиент для работы с API Open edX."""

    def __init__(self, api_base_url: str, cache_prefix: str):
        self.api_base_url = api_base_url
        self.cache_prefix = cache_prefix
        self.cache = self._init_cache()
        self.client = self._init_api_client()

    def _init_cache(self) -> Optional[memcache.Client]:
        """Инициализация кэша."""
        if settings.LMS_API_USE_MEMCACHED:
            try:
                return memcache.Client(
                    settings.MEMCACHED_ADDRESS,
                    connect_timeout=2,
                    timeout=5
                )
            except Exception as e:
                logger.error("Ошибка инициализации кэша: %s", e)
        return None

    def _init_api_client(self) -> EdxRestApiClient:
        """Инициализация API клиента с OAuth2."""
        token = EdxRestApiClient.get_oauth_access_token(
            url=f"{settings.OPENEDX_PLATFORM_URI}{constants.OPENEDX_OAUTH2_TOKEN_URL}",
            client_id=settings.OPENEDX_OAUTH2_CLIENT_ID,
            client_secret=settings.OPENEDX_OAUTH2_CLIENT_SECRET,
        )
        return EdxRestApiClient(
            self.api_base_url,
            append_slash=False,
            oauth_access_token=token[0],
            timeout=(3.05, 10)
        )


class EnrollmentApiClient(BaseLMSAPIClient):
    """Клиент для работы с API записей на курсы."""

    def __init__(self):
        super().__init__(
            api_base_url=settings.OPENEDX_ENROLLMENT_API_URI,
            cache_prefix="enrollment_api_"
        )

    def get_course_info(self, course_id: str) -> Dict[str, Any]:
        """
        Получение информации о курсе.

        Args:
            course_id: Идентификатор курса (например, course-v1:org+course+run)

        Returns:
            Словарь с данными курса

        Raises:
            XAPIBridgeCourseNotFoundError: Если курс не найден
        """
        cache_key = f"{self.cache_prefix}course_{course_id}"

        # Попытка получить данные из кэша
        if self.cache:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            except Exception as e:
                logger.warning("Ошибка чтения из кэша: %s", e)

        try:
            response = self.client.course(course_id).get(params={'include_expired': 1})
            course_data = self._parse_response(response)

            # Кэширование на 5 минут
            if self.cache and course_data:
                try:
                    self.cache.set(cache_key, course_data, expire=300)
                except Exception as e:
                    logger.warning("Ошибка записи в кэш: %s", e)

            return course_data

        except (SlumberBaseException, ConnectionError, Timeout, HttpClientError) as e:
            error_msg = f"Ошибка получения данных курса {course_id}: {str(e)}"
            logger.error(error_msg)
            raise exceptions.XAPIBridgeCourseNotFoundError(error_msg) from e

    def _parse_response(self, response: Dict) -> Dict[str, Any]:
        """Парсинг и валидация ответа API."""
        if not response.get('course_name'):
            raise exceptions.XAPIBridgeCourseNotFoundError("Невалидный ответ API")

        data = {
            'name': response['course_name'],
            'description': response.get('description', ''),
        }

        if settings.UNTI_XAPI:
            data['2035_id'] = response.get('integrate_2035_id', '').strip()

        return data


class UserApiClient(BaseLMSAPIClient):
    """Клиент для работы с API пользователей."""

    def __init__(self):
        super().__init__(
            api_base_url=settings.OPENEDX_USER_API_URI,
            cache_prefix="user_api_"
        )

    def get_edx_user_info(self, username: str) -> Dict[str, str]:
        """
        Получение информации о пользователе.

        Args:
            username: Логин пользователя в системе

        Returns:
            Словарь с данными пользователя

        Raises:
            XAPIBridgeUserNotFoundError: Если пользователь не найден
        """
        if not username:
            raise exceptions.XAPIBridgeUserNotFoundError("Пустой username")

        cache_key = f"{self.cache_prefix}user_{username}"

        # Попытка получить данные из кэша
        if self.cache:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            except Exception as e:
                logger.warning("Ошибка чтения из кэша: %s", e)

        try:
            response = self.client.accounts(username).get()
            user_data = self._parse_response(response)

            # Кэширование на 5 минут
            if self.cache and user_data:
                try:
                    self.cache.set(cache_key, user_data, expire=300)
                except Exception as e:
                    logger.warning("Ошибка записи в кэш: %s", e)

            return user_data

        except (SlumberBaseException, ConnectionError, Timeout, HttpClientError) as e:
            error_msg = f"Ошибка получения данных пользователя {username}: {str(e)}"
            logger.error(error_msg)
            raise exceptions.XAPIBridgeUserNotFoundError(error_msg) from e

    def _parse_response(self, response: Dict) -> Dict[str, str]:
        """Парсинг и валидация ответа API."""
        if not response.get('email'):
            raise exceptions.XAPIBridgeUserNotFoundError("Невалидный ответ API")

        data = {
            'email': response['email'],
            'fullname': response.get('name', ''),
        }

        if settings.UNTI_XAPI:
            data['unti_id'] = response.get('unti_id', '').strip()

        return data


# Инициализация клиентов для использования в других модулях
enrollment_api_client = EnrollmentApiClient()
user_api_client = UserApiClient()
